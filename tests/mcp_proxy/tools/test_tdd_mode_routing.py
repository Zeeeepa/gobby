"""Tests for TDD mode routing in create_task.

When tdd_mode is enabled and a task has multi-step content, the task should be
routed through TaskExpander (LLM-based) instead of regex extraction to get
proper test->implementation pairs.

TDD: These tests are written first and should fail until implementation is complete.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.app import DaemonConfig, GobbyTasksConfig, TaskExpansionConfig, TaskValidationConfig
from gobby.mcp_proxy.tools.tasks import create_task_registry
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.sync.tasks import TaskSyncManager
from gobby.tasks.expansion import TaskExpander
from gobby.workflows.definitions import WorkflowState


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def test_db(tmp_path):
    """Create a test database with migrations applied."""
    db_path = tmp_path / "test.db"
    db = LocalDatabase(str(db_path))
    run_migrations(db)
    # Create a test project
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (id, name) VALUES (?, ?)",
            ("test-project", "Test Project"),
        )
    return db


@pytest.fixture
def task_manager(test_db):
    """Create a LocalTaskManager instance."""
    return LocalTaskManager(test_db)


@pytest.fixture
def sync_manager(test_db):
    """Create a mock TaskSyncManager."""
    return MagicMock(spec=TaskSyncManager)


@pytest.fixture
def mock_task_expander():
    """Create a mock TaskExpander that returns TDD pairs."""
    expander = MagicMock(spec=TaskExpander)
    expander.expand_task = AsyncMock(return_value={
        "subtask_ids": ["gt-test1", "gt-impl1", "gt-test2", "gt-impl2"],
        "subtask_count": 4,
        "raw_response": "mock TDD response",
    })
    return expander


@pytest.fixture
def config_tdd_enabled():
    """Create a DaemonConfig with tdd_mode enabled."""
    config = MagicMock(spec=DaemonConfig)

    # Task expansion config with TDD enabled
    expansion_config = TaskExpansionConfig()
    expansion_config.enabled = True
    expansion_config.tdd_mode = True

    # Validation config
    validation_config = TaskValidationConfig()
    validation_config.auto_generate_on_create = False
    validation_config.auto_generate_on_expand = False

    # Combined config
    tasks_config = GobbyTasksConfig()
    tasks_config.expansion = expansion_config
    tasks_config.validation = validation_config
    tasks_config.show_result_on_create = False

    config.get_gobby_tasks_config.return_value = tasks_config
    return config


@pytest.fixture
def config_tdd_disabled():
    """Create a DaemonConfig with tdd_mode disabled."""
    config = MagicMock(spec=DaemonConfig)

    # Task expansion config with TDD disabled
    expansion_config = TaskExpansionConfig()
    expansion_config.enabled = True
    expansion_config.tdd_mode = False

    # Validation config
    validation_config = TaskValidationConfig()
    validation_config.auto_generate_on_create = False
    validation_config.auto_generate_on_expand = False

    # Combined config
    tasks_config = GobbyTasksConfig()
    tasks_config.expansion = expansion_config
    tasks_config.validation = validation_config
    tasks_config.show_result_on_create = False

    config.get_gobby_tasks_config.return_value = tasks_config
    return config


@pytest.fixture
def workflow_state_tdd_enabled():
    """Workflow state with tdd_mode enabled."""
    return WorkflowState(
        session_id="test-session",
        workflow_name="test-workflow",
        step="execute",
        step_entered_at=datetime.now(UTC),
        variables={"tdd_mode": True, "auto_decompose": True},
    )


@pytest.fixture
def workflow_state_tdd_disabled():
    """Workflow state with tdd_mode disabled."""
    return WorkflowState(
        session_id="test-session",
        workflow_name="test-workflow",
        step="execute",
        step_entered_at=datetime.now(UTC),
        variables={"tdd_mode": False, "auto_decompose": True},
    )


# =============================================================================
# Test: TDD mode routes multi-step tasks through TaskExpander
# =============================================================================


class TestTddModeRoutesToExpander:
    """Tests that tdd_mode=true routes multi-step tasks through TaskExpander."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_multi_step_with_tdd_mode_calls_expander(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_enabled
    ):
        """When tdd_mode=true and description is multi-step, TaskExpander should be called."""
        multi_step_description = """Implement user authentication:
1. Create user model with email and password
2. Add login endpoint with JWT
3. Implement logout endpoint"""

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={"tdd_mode": True},
            )

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_enabled,
            )
            create_task = registry.get_tool("create_task")

            result = await create_task(
                title="Add authentication",
                description=multi_step_description,
            )

            # TaskExpander.expand_task should have been called
            mock_task_expander.expand_task.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_tdd_mode_creates_test_implementation_pairs(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_enabled
    ):
        """TDD mode should result in test->implementation task pairs."""
        multi_step_description = """Add caching layer:
1. Install Redis client
2. Create cache middleware
3. Add cache invalidation"""

        # Configure expander to return TDD pairs
        mock_task_expander.expand_task = AsyncMock(return_value={
            "subtask_ids": [
                "gt-test-redis", "gt-impl-redis",
                "gt-test-middleware", "gt-impl-middleware",
                "gt-test-invalidation", "gt-impl-invalidation",
            ],
            "subtask_count": 6,
            "raw_response": "TDD pairs created",
        })

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={"tdd_mode": True},
            )

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_enabled,
            )
            create_task = registry.get_tool("create_task")

            result = await create_task(
                title="Add caching",
                description=multi_step_description,
            )

            # Result should indicate TDD expansion occurred
            assert result.get("subtask_count", 0) >= 6  # More subtasks due to TDD pairs


# =============================================================================
# Test: TDD mode disabled uses regex extraction
# =============================================================================


class TestTddModeDisabledUsesRegex:
    """Tests that tdd_mode=false uses regex extraction (current behavior)."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_tdd_disabled_uses_regex_extraction(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_disabled
    ):
        """When tdd_mode=false, multi-step tasks use regex extraction, not TaskExpander."""
        multi_step_description = """Setup project:
1. Initialize repository
2. Add dependencies
3. Configure CI/CD"""

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={"tdd_mode": False},
            )

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_disabled,
            )
            create_task = registry.get_tool("create_task")

            result = await create_task(
                title="Setup",
                description=multi_step_description,
            )

            # TaskExpander should NOT have been called
            mock_task_expander.expand_task.assert_not_called()

            # Result should show auto_decomposed (regex path was used)
            assert result.get("auto_decomposed") is True

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_single_step_task_never_calls_expander(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_enabled
    ):
        """Single-step tasks should never call TaskExpander, even with tdd_mode=true."""
        single_step_description = "Fix the typo in the README file."

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={"tdd_mode": True},
            )

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_enabled,
            )
            create_task = registry.get_tool("create_task")

            result = await create_task(
                title="Fix typo",
                description=single_step_description,
            )

            # TaskExpander should NOT be called for single-step tasks
            mock_task_expander.expand_task.assert_not_called()


# =============================================================================
# Test: TDD mode resolution from workflow state > config hierarchy
# =============================================================================


class TestTddModeResolutionHierarchy:
    """Tests that tdd_mode is resolved from workflow state > config hierarchy."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_workflow_variable_overrides_config(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_enabled
    ):
        """Workflow variable tdd_mode=false should override config tdd_mode=true."""
        multi_step_description = """Build feature:
1. Create model
2. Add API
3. Build UI"""

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            # Workflow state has tdd_mode=false (overrides config which has tdd_mode=true)
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={"tdd_mode": False},
            )

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_enabled,  # Config has tdd_mode=true
            )
            create_task = registry.get_tool("create_task")

            result = await create_task(
                title="Build feature",
                description=multi_step_description,
            )

            # Workflow variable (false) wins, so expander should NOT be called
            mock_task_expander.expand_task.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_config_used_when_workflow_variable_not_set(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_enabled
    ):
        """Config tdd_mode should be used when workflow variable is not set."""
        multi_step_description = """Add feature:
1. Step one
2. Step two
3. Step three"""

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            # Workflow state has NO tdd_mode variable
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={},  # No tdd_mode variable
            )

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_enabled,  # Config has tdd_mode=true
            )
            create_task = registry.get_tool("create_task")

            result = await create_task(
                title="Add feature",
                description=multi_step_description,
            )

            # Config (true) is used, so expander SHOULD be called
            mock_task_expander.expand_task.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_workflow_variable_true_enables_tdd(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_disabled
    ):
        """Workflow variable tdd_mode=true should enable TDD even if config is false."""
        multi_step_description = """Implement auth:
1. Create user model
2. Add login endpoint
3. Add logout endpoint"""

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            # Workflow state has tdd_mode=true (overrides config false)
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={"tdd_mode": True},
            )

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_disabled,  # Config has tdd_mode=false
            )
            create_task = registry.get_tool("create_task")

            result = await create_task(
                title="Implement auth",
                description=multi_step_description,
            )

            # Workflow variable (true) wins, so expander SHOULD be called
            mock_task_expander.expand_task.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_no_workflow_state_uses_config(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_enabled
    ):
        """When no workflow state exists, config tdd_mode should be used."""
        multi_step_description = """Setup:
1. First step
2. Second step
3. Third step"""

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            # No workflow state
            mock_get_state.return_value = None

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_enabled,  # Config has tdd_mode=true
            )
            create_task = registry.get_tool("create_task")

            result = await create_task(
                title="Setup",
                description=multi_step_description,
            )

            # Config (true) is used, so expander SHOULD be called
            mock_task_expander.expand_task.assert_called_once()


# =============================================================================
# Test: Edge cases and error handling
# =============================================================================


class TestTddModeEdgeCases:
    """Tests for edge cases in TDD mode routing."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_expander_failure_falls_back_to_regex(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_enabled
    ):
        """If TaskExpander fails, should fall back to regex extraction."""
        # Make expander fail
        mock_task_expander.expand_task = AsyncMock(
            side_effect=Exception("LLM service unavailable")
        )

        multi_step_description = """Build feature:
1. Create model
2. Add API
3. Build UI"""

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={"tdd_mode": True},
            )

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_enabled,
            )
            create_task = registry.get_tool("create_task")

            # Should not raise - should fall back to regex
            result = await create_task(
                title="Build feature",
                description=multi_step_description,
            )

            # Expander was called but failed
            mock_task_expander.expand_task.assert_called_once()

            # Fallback to regex extraction should have occurred
            # Task should still be created with auto_decomposed=True
            assert "id" in result

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_epic_type_skips_tdd_mode(
        self, task_manager, sync_manager, mock_task_expander, config_tdd_enabled
    ):
        """Epic-type tasks should skip TDD mode (epics are containers, not code)."""
        multi_step_description = """Epic phases:
1. Phase 1: Research
2. Phase 2: Implementation
3. Phase 3: Testing"""

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={"tdd_mode": True},
            )

            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=mock_task_expander,
                config=config_tdd_enabled,
            )
            create_task = registry.get_tool("create_task")

            result = await create_task(
                title="Project Epic",
                description=multi_step_description,
                task_type="epic",
            )

            # TaskExpander should NOT be called for epics
            mock_task_expander.expand_task.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_no_expander_provided_uses_regex(
        self, task_manager, sync_manager, config_tdd_enabled
    ):
        """When no TaskExpander is provided, should use regex extraction."""
        multi_step_description = """Build feature:
1. Create model
2. Add API
3. Build UI"""

        with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx, \
             patch("gobby.mcp_proxy.tools.tasks.get_workflow_state") as mock_get_state:

            mock_ctx.return_value = {"id": "test-project"}
            mock_get_state.return_value = WorkflowState(
                session_id="test",
                workflow_name="test",
                step="execute",
                step_entered_at=datetime.now(UTC),
                variables={"tdd_mode": True},
            )

            # No task_expander provided
            registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=None,  # No expander
                config=config_tdd_enabled,
            )
            create_task = registry.get_tool("create_task")

            # Should not raise - should use regex extraction
            result = await create_task(
                title="Build feature",
                description=multi_step_description,
            )

            # Task should still be created
            assert "id" in result
