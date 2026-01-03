"""Tests for task enforcement actions."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from gobby.workflows.definitions import WorkflowState
from gobby.workflows.task_enforcement_actions import require_active_task


@pytest.fixture
def mock_config():
    """Create mock config with task enforcement enabled."""
    config = MagicMock()
    config.workflow.require_task_before_edit = True
    config.workflow.protected_tools = ["Edit", "Write", "Bash"]
    return config


@pytest.fixture
def mock_task_manager():
    """Create mock task manager."""
    return MagicMock()


@pytest.fixture
def workflow_state():
    """Create a workflow state with empty variables."""
    return WorkflowState(
        session_id="test-session",
        workflow_name="test-workflow",
        step="test-step",
        step_entered_at=datetime.now(UTC),
        variables={},
    )


@pytest.mark.asyncio
class TestRequireActiveTask:
    """Tests for require_active_task action."""

    async def test_task_claimed_allows_immediately(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When task_claimed=True, tool is allowed without DB query."""
        workflow_state.variables["task_claimed"] = True

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None  # None means allow
        # Verify DB was NOT queried
        mock_task_manager.list_tasks.assert_not_called()

    async def test_no_task_claimed_blocks_protected_tool(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When task_claimed=False, protected tool is blocked."""
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "No task claimed for this session" in result["reason"]

    async def test_no_task_claimed_with_project_task_shows_hint(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When task_claimed=False but project has in_progress task, show hint."""
        mock_task = MagicMock()
        mock_task.id = "gt-existing"
        mock_task.title = "Existing task"
        mock_task_manager.list_tasks.return_value = [mock_task]

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "gt-existing" in result["reason"]
        assert "wasn't claimed by this session" in result["reason"]

    async def test_unprotected_tool_always_allowed(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Unprotected tools are allowed without any checks."""
        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Read"},  # Not in protected_tools
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None
        mock_task_manager.list_tasks.assert_not_called()

    async def test_feature_disabled_allows_all(
        self, mock_task_manager, workflow_state
    ):
        """When feature is disabled, all tools are allowed."""
        config = MagicMock()
        config.workflow.require_task_before_edit = False

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None

    async def test_no_workflow_state_falls_back_to_db_check(
        self, mock_config, mock_task_manager
    ):
        """When workflow_state is None, falls back to DB check."""
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=None,  # No workflow state
        )

        assert result is not None
        assert result["decision"] == "block"
        mock_task_manager.list_tasks.assert_called_once()

    async def test_task_claimed_false_explicitly_blocks(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When task_claimed is explicitly False, tool is blocked."""
        workflow_state.variables["task_claimed"] = False
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Write"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"

    async def test_no_config_allows_all(
        self, mock_task_manager, workflow_state
    ):
        """When config is None, all tools are allowed."""
        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=None,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None

    async def test_inject_context_explains_session_scope(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Blocking message explains session-scoped requirement."""
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Bash"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert "inject_context" in result
        assert "claim a task for this session" in result["inject_context"]
        assert "Each session must explicitly" in result["inject_context"]
