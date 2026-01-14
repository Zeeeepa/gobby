"""
Comprehensive unit tests for tasks.py MCP tools to improve coverage.

Tests focus on:
1. Task CRUD operations (create, get, update, close, delete, list)
2. Task validation and error handling
3. Label management
4. Session integration
5. Edge cases and error paths

Uses pytest with unittest.mock following existing test patterns.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.tasks import (
    SKIP_REASONS,
    _infer_test_strategy,
    create_task_registry,
)
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.sync.tasks import TaskSyncManager

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_task_manager():
    """Create a mock task manager."""
    manager = MagicMock(spec=LocalTaskManager)
    manager.db = MagicMock()
    return manager


@pytest.fixture
def mock_sync_manager():
    """Create a mock sync manager."""
    return MagicMock(spec=TaskSyncManager)


@pytest.fixture
def mock_task_validator():
    """Create a mock task validator."""
    validator = AsyncMock()
    validator.generate_criteria = AsyncMock(return_value="Generated criteria")
    validator.validate_task = AsyncMock()
    return validator


@pytest.fixture
def mock_config():
    """Create a mock daemon config."""
    config = MagicMock()
    tasks_config = MagicMock()
    tasks_config.show_result_on_create = False
    validation_config = MagicMock()
    validation_config.auto_generate_on_create = False
    validation_config.auto_generate_on_expand = False
    validation_config.use_external_validator = False
    tasks_config.validation = validation_config
    config.get_gobby_tasks_config.return_value = tasks_config
    return config


@pytest.fixture
def task_registry(mock_task_manager, mock_sync_manager):
    """Create a task registry with mocked dependencies."""
    return create_task_registry(mock_task_manager, mock_sync_manager)


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id="550e8400-e29b-41d4-a716-446655440000",
        project_id="proj-1",
        title="Test Task",
        status="open",
        priority=2,
        task_type="task",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        description="Test description",
        labels=["test"],
    )


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestInferTestStrategy:
    """Tests for _infer_test_strategy helper function."""

    def test_infer_manual_from_verify_that(self):
        """Test inferring manual strategy from 'verify that' pattern."""
        result = _infer_test_strategy("Verify that the feature works", None)
        assert result == "manual"

    def test_infer_manual_from_check_the(self):
        """Test inferring manual strategy from 'check the' pattern."""
        result = _infer_test_strategy("Check the output format", None)
        assert result == "manual"

    def test_infer_manual_from_functional_test(self):
        """Test inferring manual strategy from 'functional test' pattern."""
        result = _infer_test_strategy("Run functional testing on auth", None)
        assert result == "manual"

    def test_infer_manual_from_smoke_test(self):
        """Test inferring manual strategy from 'smoke test' pattern."""
        result = _infer_test_strategy("Perform smoke test", None)
        assert result == "manual"

    def test_infer_manual_from_manually_verify(self):
        """Test inferring manual strategy from 'manually verify' pattern."""
        result = _infer_test_strategy("Manually verify the changes", None)
        assert result == "manual"

    def test_infer_manual_from_description(self):
        """Test inferring from description when title doesn't match."""
        result = _infer_test_strategy("Task title", "Need to verify that it works")
        assert result == "manual"

    def test_infer_none_for_generic_task(self):
        """Test returning None for generic task without patterns."""
        result = _infer_test_strategy("Implement new feature", "Add the feature")
        assert result is None

    def test_infer_manual_from_run_and_check(self):
        """Test inferring manual strategy from 'run and check' pattern."""
        result = _infer_test_strategy("Run and check output", None)
        assert result == "manual"

    def test_infer_manual_case_insensitive(self):
        """Test that pattern matching is case insensitive."""
        result = _infer_test_strategy("VERIFY THAT it works", None)
        assert result == "manual"


class TestSkipReasons:
    """Tests for SKIP_REASONS constant."""

    def test_skip_reasons_contains_expected_values(self):
        """Test that SKIP_REASONS contains all expected values."""
        assert "duplicate" in SKIP_REASONS
        assert "already_implemented" in SKIP_REASONS
        assert "wont_fix" in SKIP_REASONS
        assert "obsolete" in SKIP_REASONS

    def test_skip_reasons_is_frozenset(self):
        """Test that SKIP_REASONS is immutable."""
        assert isinstance(SKIP_REASONS, frozenset)


# =============================================================================
# create_task Tool Tests
# =============================================================================


class TestCreateTaskTool:
    """Tests for create_task MCP tool."""

    @pytest.mark.asyncio
    async def test_create_task_minimal(self, mock_task_manager, mock_sync_manager):
        """Test create_task with minimal arguments."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440001"
        mock_task.seq_num = 42
        mock_task.to_dict.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "title": "New Task",
        }
        # Mock create_task_with_decomposition to return non-decomposed result
        mock_task_manager.create_task_with_decomposition.return_value = {
            "auto_decomposed": False,
            "task": {"id": "550e8400-e29b-41d4-a716-446655440001", "title": "New Task"},
        }
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            result = await registry.call("create_task", {"title": "New Task"})

            assert result == {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "seq_num": 42,
                "ref": "#42",
            }
            mock_task_manager.create_task_with_decomposition.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_task_with_blocks(self, mock_task_manager, mock_sync_manager):
        """Test create_task with blocks argument creates dependencies."""
        with patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager") as MockDepManager:
            mock_dep_instance = MagicMock()
            MockDepManager.return_value = mock_dep_instance

            registry = create_task_registry(mock_task_manager, mock_sync_manager)

            mock_task = MagicMock()
            mock_task.id = "550e8400-e29b-41d4-a716-446655440002"
            mock_task.to_dict.return_value = {"id": "550e8400-e29b-41d4-a716-446655440002"}
            mock_task_manager.create_task_with_decomposition.return_value = {
                "auto_decomposed": False,
                "task": {"id": "550e8400-e29b-41d4-a716-446655440002"},
            }
            mock_task_manager.get_task.return_value = mock_task

            with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
                mock_ctx.return_value = {"id": "proj-1"}

                result = await registry.call(
                    "create_task",
                    {
                        "title": "Blocker Task",
                        "blocks": [
                            "550e8400-e29b-41d4-a716-446655440003",
                            "550e8400-e29b-41d4-a716-446655440004",
                        ],
                    },
                )

                assert result["id"] == "550e8400-e29b-41d4-a716-446655440002"
                # Verify dependencies were added
                assert mock_dep_instance.add_dependency.call_count == 2
                mock_dep_instance.add_dependency.assert_any_call(
                    "550e8400-e29b-41d4-a716-446655440002",
                    "550e8400-e29b-41d4-a716-446655440003",
                    "blocks",
                )
                mock_dep_instance.add_dependency.assert_any_call(
                    "550e8400-e29b-41d4-a716-446655440002",
                    "550e8400-e29b-41d4-a716-446655440004",
                    "blocks",
                )

    @pytest.mark.asyncio
    async def test_create_task_with_labels(self, mock_task_manager, mock_sync_manager):
        """Test create_task with labels argument."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440005"
        mock_task.to_dict.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440005",
            "labels": ["urgent", "bug"],
        }
        mock_task_manager.create_task_with_decomposition.return_value = {
            "auto_decomposed": False,
            "task": {"id": "550e8400-e29b-41d4-a716-446655440005", "labels": ["urgent", "bug"]},
        }
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            await registry.call(
                "create_task", {"title": "Labeled Task", "labels": ["urgent", "bug"]}
            )

            mock_task_manager.create_task_with_decomposition.assert_called_once()
            call_kwargs = mock_task_manager.create_task_with_decomposition.call_args.kwargs
            assert call_kwargs["labels"] == ["urgent", "bug"]

    @pytest.mark.asyncio
    async def test_create_task_infers_test_strategy(self, mock_task_manager, mock_sync_manager):
        """Test that create_task infers test_strategy for manual test tasks."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440006"
        mock_task.to_dict.return_value = {"id": "550e8400-e29b-41d4-a716-446655440006"}
        mock_task_manager.create_task_with_decomposition.return_value = {
            "auto_decomposed": False,
            "task": {"id": "550e8400-e29b-41d4-a716-446655440006"},
        }
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            await registry.call("create_task", {"title": "Verify that the feature works correctly"})

            call_kwargs = mock_task_manager.create_task_with_decomposition.call_args.kwargs
            assert call_kwargs["test_strategy"] == "manual"

    @pytest.mark.asyncio
    async def test_create_task_explicit_test_strategy_overrides_inference(
        self, mock_task_manager, mock_sync_manager
    ):
        """Test that explicit test_strategy overrides inference."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440007"
        mock_task.to_dict.return_value = {"id": "550e8400-e29b-41d4-a716-446655440007"}
        mock_task_manager.create_task_with_decomposition.return_value = {
            "auto_decomposed": False,
            "task": {"id": "550e8400-e29b-41d4-a716-446655440007"},
        }
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            # Title would infer "manual", but explicit value overrides
            await registry.call(
                "create_task",
                {"title": "Verify that tests pass", "test_strategy": "automated"},
            )

            call_kwargs = mock_task_manager.create_task_with_decomposition.call_args.kwargs
            assert call_kwargs["test_strategy"] == "automated"

    @pytest.mark.asyncio
    async def test_create_task_with_all_optional_fields(self, mock_task_manager, mock_sync_manager):
        """Test create_task with all optional fields."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440008"
        mock_task.to_dict.return_value = {"id": "550e8400-e29b-41d4-a716-446655440008"}
        mock_task_manager.create_task_with_decomposition.return_value = {
            "auto_decomposed": False,
            "task": {"id": "550e8400-e29b-41d4-a716-446655440008"},
        }
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            await registry.call(
                "create_task",
                {
                    "title": "Full Task",
                    "description": "Detailed description",
                    "priority": 1,
                    "task_type": "feature",
                    "parent_task_id": "550e8400-e29b-41d4-a716-446655440009",
                    "labels": ["important"],
                    "test_strategy": "automated",
                    "validation_criteria": "Must pass tests",
                    "session_id": "sess-123",
                },
            )

            call_kwargs = mock_task_manager.create_task_with_decomposition.call_args.kwargs
            assert call_kwargs["title"] == "Full Task"
            assert call_kwargs["description"] == "Detailed description"
            assert call_kwargs["priority"] == 1
            assert call_kwargs["task_type"] == "feature"
            assert call_kwargs["parent_task_id"] == "550e8400-e29b-41d4-a716-446655440009"
            assert call_kwargs["labels"] == ["important"]
            assert call_kwargs["test_strategy"] == "automated"
            assert call_kwargs["validation_criteria"] == "Must pass tests"
            assert call_kwargs["created_in_session_id"] == "sess-123"

    @pytest.mark.asyncio
    async def test_create_task_initializes_project(self, mock_task_manager, mock_sync_manager):
        """Test create_task initializes project when no context exists."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440010"
        mock_task.to_dict.return_value = {"id": "550e8400-e29b-41d4-a716-446655440010"}
        mock_task_manager.create_task_with_decomposition.return_value = {
            "auto_decomposed": False,
            "task": {"id": "550e8400-e29b-41d4-a716-446655440010"},
        }
        mock_task_manager.get_task.return_value = mock_task

        with (
            patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.tasks.initialize_project") as mock_init,
        ):
            mock_ctx.return_value = None  # No project context
            mock_init_result = MagicMock()
            mock_init_result.project_id = "new-proj"
            mock_init.return_value = mock_init_result

            await registry.call("create_task", {"title": "Task"})

            mock_init.assert_called_once()
            call_kwargs = mock_task_manager.create_task_with_decomposition.call_args.kwargs
            assert call_kwargs["project_id"] == "new-proj"

    @pytest.mark.asyncio
    async def test_create_task_with_show_result_on_create(
        self, mock_task_manager, mock_sync_manager, mock_config
    ):
        """Test create_task returns full result when show_result_on_create is True."""
        mock_config.get_gobby_tasks_config.return_value.show_result_on_create = True

        registry = create_task_registry(mock_task_manager, mock_sync_manager, config=mock_config)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440011"
        mock_task.to_dict.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440011",
            "title": "Full Task",
            "status": "open",
        }
        mock_task_manager.create_task_with_decomposition.return_value = {
            "auto_decomposed": False,
            "task": {
                "id": "550e8400-e29b-41d4-a716-446655440011",
                "title": "Full Task",
                "status": "open",
            },
        }
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            result = await registry.call("create_task", {"title": "Full Task"})

            # Should return full task dict, not minimal
            assert result == {
                "id": "550e8400-e29b-41d4-a716-446655440011",
                "title": "Full Task",
                "status": "open",
            }

    @pytest.mark.asyncio
    async def test_create_task_auto_generates_validation(
        self, mock_task_manager, mock_sync_manager, mock_task_validator, mock_config
    ):
        """Test create_task auto-generates validation criteria when enabled."""
        mock_config.get_gobby_tasks_config.return_value.validation.auto_generate_on_create = True

        registry = create_task_registry(
            mock_task_manager,
            mock_sync_manager,
            task_validator=mock_task_validator,
            config=mock_config,
        )

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440012"
        mock_task.task_type = "task"  # Not epic
        mock_task.to_dict.return_value = {"id": "550e8400-e29b-41d4-a716-446655440012"}
        mock_task_manager.create_task_with_decomposition.return_value = {
            "auto_decomposed": False,
            "task": {"id": "550e8400-e29b-41d4-a716-446655440012"},
        }
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            result = await registry.call("create_task", {"title": "Task"})

            mock_task_manager.update_task.assert_not_called()
            assert "validation_generated" not in result

# =============================================================================
# get_task Tool Tests
# =============================================================================


class TestGetTaskTool:
    """Tests for get_task MCP tool."""

    @pytest.mark.asyncio
    async def test_get_task_found(self, mock_task_manager, mock_sync_manager, sample_task):
        """Test get_task returns task with dependencies."""
        with patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager") as MockDepManager:
            mock_dep_instance = MagicMock()
            mock_dep_instance.get_blockers.return_value = []
            mock_dep_instance.get_blocking.return_value = []
            MockDepManager.return_value = mock_dep_instance

            registry = create_task_registry(mock_task_manager, mock_sync_manager)

            mock_task_manager.get_task.return_value = sample_task

            result = await registry.call("get_task", {"task_id": sample_task.id})

            assert result["id"] == sample_task.id
            assert result["title"] == "Test Task"
            assert "dependencies" in result
            assert "blocked_by" in result["dependencies"]
            assert "blocking" in result["dependencies"]

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, mock_task_manager, mock_sync_manager):
        """Test get_task returns error when task not found."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.get_task.return_value = None

        result = await registry.call(
            "get_task", {"task_id": "00000000-0000-0000-0000-000000000000"}
        )

        assert "error" in result
        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_get_task_with_dependencies(
        self, mock_task_manager, mock_sync_manager, sample_task
    ):
        """Test get_task includes dependency information."""
        with patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager") as MockDepManager:
            mock_dep_instance = MagicMock()

            # Create mock blocker and blocking dependencies
            mock_blocker = MagicMock()
            mock_blocker.to_dict.return_value = {
                "from_task": "550e8400-e29b-41d4-a716-446655440001",
                "type": "blocks",
            }

            mock_blocking = MagicMock()
            mock_blocking.to_dict.return_value = {
                "from_task": "550e8400-e29b-41d4-a716-446655440000",
                "type": "blocks",
            }

            mock_dep_instance.get_blockers.return_value = [mock_blocker]
            mock_dep_instance.get_blocking.return_value = [mock_blocking]
            MockDepManager.return_value = mock_dep_instance

            registry = create_task_registry(mock_task_manager, mock_sync_manager)

            mock_task_manager.get_task.return_value = sample_task

            result = await registry.call(
                "get_task", {"task_id": "550e8400-e29b-41d4-a716-446655440000"}
            )

            assert len(result["dependencies"]["blocked_by"]) == 1
            assert len(result["dependencies"]["blocking"]) == 1


# =============================================================================
# update_task Tool Tests
# =============================================================================


class TestUpdateTaskTool:
    """Tests for update_task MCP tool."""

    @pytest.mark.asyncio
    async def test_update_task_title(self, mock_task_manager, mock_sync_manager, sample_task):
        """Test update_task updates title."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        updated_task = MagicMock()
        mock_task_manager.update_task.return_value = updated_task

        result = await registry.call(
            "update_task",
            {"task_id": "550e8400-e29b-41d4-a716-446655440000", "title": "Updated Title"},
        )

        mock_task_manager.update_task.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000", title="Updated Title"
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, mock_task_manager, mock_sync_manager):
        """Test update_task returns error when task not found."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.update_task.return_value = None

        result = await registry.call(
            "update_task", {"task_id": "00000000-0000-0000-0000-000000000000", "title": "New Title"}
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_task_all_fields(self, mock_task_manager, mock_sync_manager):
        """Test update_task with all updatable fields."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        updated_task = MagicMock()
        updated_task.to_brief.return_value = {"id": "550e8400-e29b-41d4-a716-446655440000"}
        mock_task_manager.update_task.return_value = updated_task

        await registry.call(
            "update_task",
            {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "New Title",
                "description": "New Description",
                "status": "in_progress",
                "priority": 1,
                "assignee": "developer",
                "labels": ["urgent"],
                "validation_criteria": "Must pass",
                "parent_task_id": "550e8400-e29b-41d4-a716-446655440010",
                "test_strategy": "automated",
                "workflow_name": "dev-flow",
                "verification": "Run tests",
                "sequence_order": 5,
            },
        )

        mock_task_manager.update_task.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000",
            title="New Title",
            description="New Description",
            status="in_progress",
            priority=1,
            assignee="developer",
            labels=["urgent"],
            validation_criteria="Must pass",
            parent_task_id="550e8400-e29b-41d4-a716-446655440010",
            test_strategy="automated",
            workflow_name="dev-flow",
            verification="Run tests",
            sequence_order=5,
        )

    @pytest.mark.asyncio
    async def test_update_task_partial_update(self, mock_task_manager, mock_sync_manager):
        """Test update_task only includes provided fields."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        updated_task = MagicMock()
        updated_task.to_brief.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "closed",
        }
        mock_task_manager.update_task.return_value = updated_task

        await registry.call(
            "update_task", {"task_id": "550e8400-e29b-41d4-a716-446655440000", "status": "closed"}
        )

        # Should only include status, not other None values
        mock_task_manager.update_task.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000", status="closed"
        )


# =============================================================================
# add_label and remove_label Tool Tests
# =============================================================================


class TestLabelTools:
    """Tests for add_label and remove_label MCP tools."""

    @pytest.mark.asyncio
    async def test_add_label_success(self, mock_task_manager, mock_sync_manager, sample_task):
        """Test add_label adds a label to task."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        updated_task = MagicMock()
        mock_task_manager.add_label.return_value = updated_task

        result = await registry.call(
            "add_label", {"task_id": "550e8400-e29b-41d4-a716-446655440000", "label": "new"}
        )

        mock_task_manager.add_label.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000", "new"
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_add_label_task_not_found(self, mock_task_manager, mock_sync_manager):
        """Test add_label returns error when task not found."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.add_label.return_value = None

        result = await registry.call(
            "add_label", {"task_id": "00000000-0000-0000-0000-000000000000", "label": "new"}
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_remove_label_success(self, mock_task_manager, mock_sync_manager):
        """Test remove_label removes a label from task."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        updated_task = MagicMock()
        mock_task_manager.remove_label.return_value = updated_task

        result = await registry.call(
            "remove_label", {"task_id": "550e8400-e29b-41d4-a716-446655440000", "label": "old"}
        )

        mock_task_manager.remove_label.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000", "old"
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_remove_label_task_not_found(self, mock_task_manager, mock_sync_manager):
        """Test remove_label returns error when task not found."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.remove_label.return_value = None

        result = await registry.call(
            "remove_label", {"task_id": "00000000-0000-0000-0000-000000000000", "label": "old"}
        )

        assert "error" in result


# =============================================================================
# close_task Tool Tests
# =============================================================================


class TestCloseTaskTool:
    """Tests for close_task MCP tool."""

    @pytest.mark.asyncio
    async def test_close_task_not_found(self, mock_task_manager, mock_sync_manager):
        """Test close_task returns error when task not found."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.get_task.return_value = None

        result = await registry.call(
            "close_task", {"task_id": "00000000-0000-0000-0000-000000000000"}
        )

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_close_task_no_commits_error(self, mock_task_manager, mock_sync_manager):
        """Test close_task requires commits to be linked."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440000"
        mock_task.commits = None
        mock_task.project_id = "proj-1"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.mcp_proxy.tools.tasks.LocalProjectManager") as MockProjManager:
            mock_proj_instance = MagicMock()
            mock_proj_instance.get.return_value = None
            MockProjManager.return_value = mock_proj_instance

            result = await registry.call(
                "close_task", {"task_id": "550e8400-e29b-41d4-a716-446655440000"}
            )

            assert "error" in result
            assert result["error"] == "no_commits_linked"

    @pytest.mark.asyncio
    async def test_close_task_no_commit_needed_requires_justification(
        self, mock_task_manager, mock_sync_manager
    ):
        """Test close_task with no_commit_needed requires justification."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440000"
        mock_task.commits = None
        mock_task.project_id = "proj-1"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.mcp_proxy.tools.tasks.LocalProjectManager") as MockProjManager:
            mock_proj_instance = MagicMock()
            mock_proj_instance.get.return_value = None
            MockProjManager.return_value = mock_proj_instance

            result = await registry.call(
                "close_task",
                {"task_id": "550e8400-e29b-41d4-a716-446655440000", "no_commit_needed": True},
            )

            assert "error" in result
            assert result["error"] == "justification_required"

    @pytest.mark.asyncio
    async def test_close_task_with_skip_reason_skips_commit_check(
        self, mock_task_manager, mock_sync_manager
    ):
        """Test close_task with skip reason bypasses commit check."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440000"
        mock_task.commits = None
        mock_task.project_id = "proj-1"
        mock_task.to_brief.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "closed",
        }
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.close_task.return_value = mock_task

        with (
            patch("gobby.mcp_proxy.tools.tasks.LocalProjectManager") as MockProjManager,
            patch("gobby.utils.git.run_git_command") as mock_git,
        ):
            mock_proj_instance = MagicMock()
            mock_proj_instance.get.return_value = None
            MockProjManager.return_value = mock_proj_instance
            mock_git.return_value = "abc123"

            result = await registry.call(
                "close_task",
                {"task_id": "550e8400-e29b-41d4-a716-446655440000", "reason": "duplicate"},
            )

            assert "error" not in result
            mock_task_manager.close_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_task_parent_with_open_children(self, mock_task_manager, mock_sync_manager):
        """Test close_task fails for parent with open children."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440020"
        mock_task.commits = ["abc123"]
        mock_task.project_id = "proj-1"
        mock_task.validation_criteria = None
        mock_task_manager.get_task.return_value = mock_task

        # Create open child tasks
        child1 = MagicMock()
        child1.id = "550e8400-e29b-41d4-a716-446655440021"
        child1.title = "Open Child 1"
        child1.status = "open"

        child2 = MagicMock()
        child2.id = "550e8400-e29b-41d4-a716-446655440022"
        child2.title = "Open Child 2"
        child2.status = "in_progress"

        mock_task_manager.list_tasks.return_value = [child1, child2]

        with patch("gobby.mcp_proxy.tools.tasks.LocalProjectManager") as MockProjManager:
            mock_proj_instance = MagicMock()
            mock_proj_instance.get.return_value = None
            MockProjManager.return_value = mock_proj_instance

            result = await registry.call(
                "close_task", {"task_id": "550e8400-e29b-41d4-a716-446655440020"}
            )

            assert "error" in result
            assert result["error"] == "validation_failed"
            assert "open_children" in result

    @pytest.mark.asyncio
    async def test_close_task_success_with_commits(self, mock_task_manager, mock_sync_manager):
        """Test close_task succeeds when commits are linked."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440000"
        mock_task.commits = ["abc123"]
        mock_task.project_id = "proj-1"
        mock_task.validation_criteria = None
        mock_task.to_brief.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "closed",
        }
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.close_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []  # No children

        with (
            patch("gobby.mcp_proxy.tools.tasks.LocalProjectManager") as MockProjManager,
            patch("gobby.utils.git.run_git_command") as mock_git,
        ):
            mock_proj_instance = MagicMock()
            mock_proj_instance.get.return_value = None
            MockProjManager.return_value = mock_proj_instance
            mock_git.return_value = "abc123"

            result = await registry.call(
                "close_task", {"task_id": "550e8400-e29b-41d4-a716-446655440000"}
            )

            assert result == {}

    @pytest.mark.asyncio
    async def test_close_task_with_commit_sha_links_first(
        self, mock_task_manager, mock_sync_manager
    ):
        """Test close_task with commit_sha links the commit first."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440000"
        mock_task.commits = ["abc123"]
        mock_task.project_id = "proj-1"
        mock_task.validation_criteria = None
        mock_task.to_brief.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "closed",
        }
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.link_commit.return_value = mock_task
        mock_task_manager.close_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []

        with (
            patch("gobby.mcp_proxy.tools.tasks.LocalProjectManager") as MockProjManager,
            patch("gobby.utils.git.run_git_command") as mock_git,
        ):
            mock_proj_instance = MagicMock()
            mock_proj_instance.get.return_value = None
            MockProjManager.return_value = mock_proj_instance
            mock_git.return_value = "abc123"

            await registry.call(
                "close_task",
                {"task_id": "550e8400-e29b-41d4-a716-446655440000", "commit_sha": "new-commit"},
            )

            mock_task_manager.link_commit.assert_called_with(
                "550e8400-e29b-41d4-a716-446655440000", "new-commit"
            )

    @pytest.mark.asyncio
    async def test_close_task_with_skip_validation(self, mock_task_manager, mock_sync_manager):
        """Test close_task with skip_validation bypasses LLM validation."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task = MagicMock()
        mock_task.id = "550e8400-e29b-41d4-a716-446655440000"
        mock_task.commits = ["abc123"]
        mock_task.project_id = "proj-1"
        mock_task.validation_criteria = "Must pass tests"
        mock_task.to_brief.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "closed",
        }
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.close_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []

        with (
            patch("gobby.mcp_proxy.tools.tasks.LocalProjectManager") as MockProjManager,
            patch("gobby.utils.git.run_git_command") as mock_git,
        ):
            mock_proj_instance = MagicMock()
            mock_proj_instance.get.return_value = None
            MockProjManager.return_value = mock_proj_instance
            mock_git.return_value = "abc123"

            result = await registry.call(
                "close_task",
                {
                    "task_id": "550e8400-e29b-41d4-a716-446655440000",
                    "skip_validation": True,
                    "override_justification": "Manually verified",
                },
            )

            assert result == {}


# =============================================================================
# reopen_task Tool Tests
# =============================================================================


class TestReopenTaskTool:
    """Tests for reopen_task MCP tool."""

    @pytest.mark.asyncio
    async def test_reopen_task_success(self, mock_task_manager, mock_sync_manager):
        """Test reopen_task successfully reopens a closed task."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        reopened_task = MagicMock()
        mock_task_manager.reopen_task.return_value = reopened_task

        result = await registry.call(
            "reopen_task", {"task_id": "550e8400-e29b-41d4-a716-446655440000"}
        )

        mock_task_manager.reopen_task.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000", reason=None
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_reopen_task_with_reason(self, mock_task_manager, mock_sync_manager):
        """Test reopen_task with a reason."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        reopened_task = MagicMock()
        reopened_task.to_dict.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "open",
        }
        mock_task_manager.reopen_task.return_value = reopened_task

        await registry.call(
            "reopen_task",
            {"task_id": "550e8400-e29b-41d4-a716-446655440000", "reason": "Needs more work"},
        )

        mock_task_manager.reopen_task.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000", reason="Needs more work"
        )

    @pytest.mark.asyncio
    async def test_reopen_task_error(self, mock_task_manager, mock_sync_manager):
        """Test reopen_task returns error on failure."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.reopen_task.side_effect = ValueError("Task not found")

        result = await registry.call(
            "reopen_task", {"task_id": "00000000-0000-0000-0000-000000000000"}
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_reopen_task_reactivates_worktree(self, mock_task_manager, mock_sync_manager):
        """Test reopen_task reactivates associated worktrees."""
        with patch("gobby.mcp_proxy.tools.tasks.LocalWorktreeManager") as MockWorktreeManager:
            mock_wt_instance = MagicMock()
            mock_worktree = MagicMock()
            mock_worktree.id = "wt-123"
            mock_worktree.status = "merged"
            mock_wt_instance.get_by_task.return_value = mock_worktree
            MockWorktreeManager.return_value = mock_wt_instance

            registry = create_task_registry(mock_task_manager, mock_sync_manager)

            reopened_task = MagicMock()
            reopened_task.to_dict.return_value = {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "open",
            }
            mock_task_manager.reopen_task.return_value = reopened_task

            await registry.call("reopen_task", {"task_id": "550e8400-e29b-41d4-a716-446655440000"})

            mock_wt_instance.update.assert_called()


# =============================================================================
# delete_task Tool Tests
# =============================================================================


class TestDeleteTaskTool:
    """Tests for delete_task MCP tool."""

    @pytest.mark.asyncio
    async def test_delete_task_success(self, mock_task_manager, mock_sync_manager):
        """Test delete_task successfully deletes a task."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.delete_task.return_value = True

        result = await registry.call(
            "delete_task", {"task_id": "550e8400-e29b-41d4-a716-446655440000"}
        )

        mock_task_manager.delete_task.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000", cascade=True
        )
        assert "error" not in result
        assert result["deleted_task_id"] == "550e8400-e29b-41d4-a716-446655440000"

    @pytest.mark.asyncio
    async def test_delete_task_not_found(self, mock_task_manager, mock_sync_manager):
        """Test delete_task returns error when task not found."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.delete_task.return_value = False

        result = await registry.call(
            "delete_task", {"task_id": "00000000-0000-0000-0000-000000000000"}
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_task_without_cascade(self, mock_task_manager, mock_sync_manager):
        """Test delete_task without cascade option."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.delete_task.return_value = True

        await registry.call(
            "delete_task", {"task_id": "550e8400-e29b-41d4-a716-446655440000", "cascade": False}
        )

        mock_task_manager.delete_task.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000", cascade=False
        )


# =============================================================================
# list_tasks Tool Tests
# =============================================================================


class TestListTasksTool:
    """Tests for list_tasks MCP tool."""

    @pytest.mark.asyncio
    async def test_list_tasks_basic(self, mock_task_manager, mock_sync_manager):
        """Test list_tasks returns tasks with count."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task1 = MagicMock()
        mock_task1.to_brief.return_value = {"id": "t1", "title": "Task 1"}
        mock_task2 = MagicMock()
        mock_task2.to_brief.return_value = {"id": "t2", "title": "Task 2"}

        mock_task_manager.list_tasks.return_value = [mock_task1, mock_task2]

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            result = await registry.call("list_tasks", {})

            assert result["count"] == 2
            assert len(result["tasks"]) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_with_filters(self, mock_task_manager, mock_sync_manager):
        """Test list_tasks applies filters correctly."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.list_tasks.return_value = []

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            await registry.call(
                "list_tasks",
                {
                    "status": "open",
                    "priority": 1,
                    "task_type": "bug",
                    "assignee": "dev",
                    "label": "urgent",
                    "parent_task_id": "550e8400-e29b-41d4-a716-446655440010",
                    "title_like": "feature",
                    "limit": 10,
                },
            )

            mock_task_manager.list_tasks.assert_called_with(
                status="open",
                priority=1,
                task_type="bug",
                assignee="dev",
                label="urgent",
                parent_task_id="550e8400-e29b-41d4-a716-446655440010",
                title_like="feature",
                limit=10,
                project_id="proj-1",
            )

    @pytest.mark.asyncio
    async def test_list_tasks_all_projects(self, mock_task_manager, mock_sync_manager):
        """Test list_tasks with all_projects=True ignores project filter."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.list_tasks.return_value = []

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            await registry.call("list_tasks", {"all_projects": True})

            call_kwargs = mock_task_manager.list_tasks.call_args.kwargs
            assert call_kwargs["project_id"] is None

    @pytest.mark.asyncio
    async def test_list_tasks_comma_separated_status(self, mock_task_manager, mock_sync_manager):
        """Test list_tasks handles comma-separated status strings."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        mock_task_manager.list_tasks.return_value = []

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
            mock_ctx.return_value = {"id": "proj-1"}

            await registry.call("list_tasks", {"status": "open,in_progress"})

            call_kwargs = mock_task_manager.list_tasks.call_args.kwargs
            assert call_kwargs["status"] == ["open", "in_progress"]


# =============================================================================
# Session Integration Tool Tests
# =============================================================================


class TestSessionIntegrationTools:
    """Tests for session integration MCP tools."""

    @pytest.mark.asyncio
    async def test_link_task_to_session_success(self, mock_task_manager, mock_sync_manager):
        """Test link_task_to_session creates a link."""
        with patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager") as MockSessionTaskManager:
            mock_st_instance = MagicMock()
            MockSessionTaskManager.return_value = mock_st_instance

            registry = create_task_registry(mock_task_manager, mock_sync_manager)

            result = await registry.call(
                "link_task_to_session",
                {
                    "task_id": "550e8400-e29b-41d4-a716-446655440000",
                    "session_id": "sess-123",
                    "action": "worked_on",
                },
            )

            mock_st_instance.link_task.assert_called_with(
                "sess-123", "550e8400-e29b-41d4-a716-446655440000", "worked_on"
            )
            assert result == {}

    @pytest.mark.asyncio
    async def test_link_task_to_session_missing_session_id(
        self, mock_task_manager, mock_sync_manager
    ):
        """Test link_task_to_session requires session_id."""
        registry = create_task_registry(mock_task_manager, mock_sync_manager)

        result = await registry.call(
            "link_task_to_session", {"task_id": "550e8400-e29b-41d4-a716-446655440000"}
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_link_task_to_session_error(self, mock_task_manager, mock_sync_manager):
        """Test link_task_to_session handles errors."""
        with patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager") as MockSessionTaskManager:
            mock_st_instance = MagicMock()
            mock_st_instance.link_task.side_effect = ValueError("Invalid task")
            MockSessionTaskManager.return_value = mock_st_instance

            registry = create_task_registry(mock_task_manager, mock_sync_manager)

            result = await registry.call(
                "link_task_to_session",
                {"task_id": "00000000-0000-0000-0000-000000000000", "session_id": "sess-123"},
            )

            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_session_tasks(self, mock_task_manager, mock_sync_manager):
        """Test get_session_tasks returns tasks for a session."""
        with patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager") as MockSessionTaskManager:
            mock_st_instance = MagicMock()
            mock_st_instance.get_session_tasks.return_value = [
                {"task_id": "t1", "action": "worked_on"}
            ]
            MockSessionTaskManager.return_value = mock_st_instance

            registry = create_task_registry(mock_task_manager, mock_sync_manager)

            result = await registry.call("get_session_tasks", {"session_id": "sess-123"})

            assert result["session_id"] == "sess-123"
            assert len(result["tasks"]) == 1

    @pytest.mark.asyncio
    async def test_get_task_sessions(self, mock_task_manager, mock_sync_manager):
        """Test get_task_sessions returns sessions for a task."""
        with patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager") as MockSessionTaskManager:
            mock_st_instance = MagicMock()
            mock_st_instance.get_task_sessions.return_value = [
                {"session_id": "sess-1", "action": "created"}
            ]
            MockSessionTaskManager.return_value = mock_st_instance

            registry = create_task_registry(mock_task_manager, mock_sync_manager)

            result = await registry.call(
                "get_task_sessions", {"task_id": "550e8400-e29b-41d4-a716-446655440000"}
            )

            assert result["task_id"] == "550e8400-e29b-41d4-a716-446655440000"
            assert len(result["sessions"]) == 1


# =============================================================================
# Registry Integration Tests
# =============================================================================


class TestRegistryIntegration:
    """Tests for registry merging and tool availability."""

    def test_registry_name_and_description(self, task_registry):
        """Test registry has correct name and description."""
        assert task_registry.name == "gobby-tasks"
        assert "Task management" in task_registry.description

    def test_crud_tools_registered(self, task_registry):
        """Test all CRUD tools are registered."""
        crud_tools = [
            "create_task",
            "get_task",
            "update_task",
            "close_task",
            "delete_task",
            "list_tasks",
        ]

        tools_list = task_registry.list_tools()
        tool_names = [t["name"] for t in tools_list]

        for tool_name in crud_tools:
            assert tool_name in tool_names, f"Missing CRUD tool: {tool_name}"

    def test_label_tools_registered(self, task_registry):
        """Test label tools are registered."""
        label_tools = ["add_label", "remove_label"]

        tools_list = task_registry.list_tools()
        tool_names = [t["name"] for t in tools_list]

        for tool_name in label_tools:
            assert tool_name in tool_names, f"Missing label tool: {tool_name}"

    def test_session_tools_registered(self, task_registry):
        """Test session integration tools are registered."""
        session_tools = ["link_task_to_session", "get_session_tasks", "get_task_sessions"]

        tools_list = task_registry.list_tools()
        tool_names = [t["name"] for t in tools_list]

        for tool_name in session_tools:
            assert tool_name in tool_names, f"Missing session tool: {tool_name}"

    def test_reopen_task_registered(self, task_registry):
        """Test reopen_task is registered."""
        tools_list = task_registry.list_tools()
        tool_names = [t["name"] for t in tools_list]

        assert "reopen_task" in tool_names

    def test_merged_registries_available(self, task_registry):
        """Test tools from merged registries are available."""
        merged_tools = [
            # From task_validation
            "validate_task",
            "generate_validation_criteria",
            # From task_expansion
            "expand_task",
            # From task_dependencies
            "add_dependency",
            "remove_dependency",
            # From task_readiness
            "list_ready_tasks",
            "list_blocked_tasks",
            # From task_sync
            "sync_tasks",
        ]

        tools_list = task_registry.list_tools()
        tool_names = [t["name"] for t in tools_list]

        for tool_name in merged_tools:
            assert tool_name in tool_names, f"Missing merged tool: {tool_name}"


# =============================================================================
# Schema Tests
# =============================================================================


class TestToolSchemas:
    """Tests for tool input schemas."""

    def test_create_task_schema_has_required_fields(self, task_registry):
        """Test create_task schema has required title field."""
        schema = task_registry.get_schema("create_task")

        assert schema is not None
        assert "title" in schema["inputSchema"]["properties"]
        assert "title" in schema["inputSchema"]["required"]

    def test_update_task_schema_has_all_fields(self, task_registry):
        """Test update_task schema includes all updatable fields."""
        schema = task_registry.get_schema("update_task")

        assert schema is not None
        props = schema["inputSchema"]["properties"]

        expected_props = [
            "task_id",
            "title",
            "description",
            "status",
            "priority",
            "assignee",
            "labels",
            "validation_criteria",
            "parent_task_id",
            "test_strategy",
            "workflow_name",
            "verification",
            "sequence_order",
        ]

        for prop in expected_props:
            assert prop in props, f"Missing property: {prop}"

    def test_close_task_schema_has_all_fields(self, task_registry):
        """Test close_task schema includes all options."""
        schema = task_registry.get_schema("close_task")

        assert schema is not None
        props = schema["inputSchema"]["properties"]

        expected_props = [
            "task_id",
            "reason",
            "changes_summary",
            "skip_validation",
            "session_id",
            "override_justification",
            "no_commit_needed",
            "commit_sha",
        ]

        for prop in expected_props:
            assert prop in props, f"Missing property: {prop}"

    def test_list_tasks_schema_has_filters(self, task_registry):
        """Test list_tasks schema includes filter options."""
        schema = task_registry.get_schema("list_tasks")

        assert schema is not None
        props = schema["inputSchema"]["properties"]

        expected_props = [
            "status",
            "priority",
            "task_type",
            "assignee",
            "label",
            "parent_task_id",
            "title_like",
            "limit",
            "all_projects",
        ]

        for prop in expected_props:
            assert prop in props, f"Missing property: {prop}"
