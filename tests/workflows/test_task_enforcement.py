"""Tests for task enforcement actions."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from gobby.workflows.definitions import WorkflowState
from gobby.workflows.task_enforcement_actions import (
    require_active_task,
    validate_session_task_scope,
)


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

    async def test_feature_disabled_allows_all(self, mock_task_manager, workflow_state):
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

    async def test_no_workflow_state_falls_back_to_db_check(self, mock_config, mock_task_manager):
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

    async def test_no_config_allows_all(self, mock_task_manager, workflow_state):
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

    async def test_new_session_starts_without_task_claimed(self, mock_config, mock_task_manager):
        """New sessions start without task_claimed variable (blocks protected tools).

        This verifies session isolation - a fresh session has no task_claimed
        and cannot use protected tools until it claims a task.
        """
        # Simulate a fresh session with new WorkflowState
        fresh_state = WorkflowState(
            session_id="new-session-123",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={},  # Empty - no task_claimed
        )
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="new-session-123",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=fresh_state,
        )

        # New session should be blocked from protected tools
        assert result is not None
        assert result["decision"] == "block"
        # Verify task_claimed is not in variables
        assert "task_claimed" not in fresh_state.variables

    async def test_error_shown_once_then_short_reminder(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """First block shows full error, subsequent blocks show short reminder."""
        mock_task_manager.list_tasks.return_value = []

        # First call - should get full error
        result1 = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result1 is not None
        assert result1["decision"] == "block"
        assert "Each session must explicitly" in result1["inject_context"]
        assert workflow_state.variables.get("task_error_shown") is True

        # Second call - should get short reminder
        result2 = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Write"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result2 is not None
        assert result2["decision"] == "block"
        assert "see previous error" in result2["inject_context"]
        assert "Each session must explicitly" not in result2["inject_context"]

    async def test_error_dedup_without_workflow_state(self, mock_config, mock_task_manager):
        """Error dedup gracefully handles missing workflow_state (no dedup)."""
        mock_task_manager.list_tasks.return_value = []

        # First call without workflow_state
        result1 = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=None,
        )

        assert result1 is not None
        assert result1["decision"] == "block"
        # Should get full error since we can't track state
        assert "Each session must explicitly" in result1["inject_context"]

        # Second call also without workflow_state - still gets full error
        result2 = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Write"},
            project_id="proj-123",
            workflow_state=None,
        )

        assert result2 is not None
        assert result2["decision"] == "block"
        # Without state, each call shows full error
        assert "Each session must explicitly" in result2["inject_context"]


class TestValidateSessionTaskScope:
    """Tests for validate_session_task_scope action."""

    @pytest.fixture
    def workflow_state_with_session_task(self):
        """Create a workflow state with session_task set."""
        return WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": "epic-1"},
        )

    async def test_no_session_task_allows_all(self, mock_task_manager, workflow_state):
        """When no session_task is set, any task can be claimed."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state,
            event_data=event_data,
        )

        assert result is None  # Allowed

    async def test_descendant_task_allowed(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """Task that is descendant of session_task is allowed."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "child-1", "status": "in_progress"}},
        }

        # Mock is_descendant_of to return True
        with patch("gobby.workflows.task_enforcement_actions.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = True

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state_with_session_task,
                event_data=event_data,
            )

        assert result is None  # Allowed
        mock_descendant.assert_called_once_with(mock_task_manager, "child-1", "epic-1")

    async def test_non_descendant_task_blocked(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """Task outside session_task hierarchy is blocked."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "other-task", "status": "in_progress"}},
        }

        # Mock is_descendant_of to return False
        with patch("gobby.workflows.task_enforcement_actions.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = False

            # Mock get_task for error message
            mock_session_task = MagicMock()
            mock_session_task.title = "My Epic"
            mock_task_manager.get_task.return_value = mock_session_task

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state_with_session_task,
                event_data=event_data,
            )

        assert result is not None
        assert result["decision"] == "block"
        assert "not within the session_task scope" in result["reason"]
        assert "epic-1" in result["reason"]
        assert "suggest_next_task" in result["reason"]

    async def test_non_update_task_tool_allowed(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """Non-update_task tool calls are not affected."""
        event_data = {
            "tool_name": "create_task",
            "tool_input": {"arguments": {"title": "New task"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None  # Allowed - not an update_task call

    async def test_non_in_progress_status_allowed(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """Setting status to something other than in_progress is allowed."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "blocked"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None  # Allowed - not claiming (in_progress)

    async def test_no_workflow_state_allows(self, mock_task_manager):
        """When no workflow state, scope check is skipped."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=None,
            event_data=event_data,
        )

        assert result is None  # Allowed - no workflow state to check

    async def test_no_task_manager_allows(self, workflow_state_with_session_task):
        """When no task manager, scope check is skipped."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=None,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None  # Allowed - no task manager to check

    async def test_wildcard_allows_all(self, mock_task_manager):
        """When session_task='*', all tasks are allowed."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": "*"},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state,
            event_data=event_data,
        )

        assert result is None  # Allowed - wildcard means all tasks

    async def test_array_allows_descendant_of_any(self, mock_task_manager):
        """When session_task is array, task must be descendant of ANY."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": ["epic-1", "epic-2"]},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "child-of-epic-2", "status": "in_progress"}},
        }

        # Mock is_descendant_of: False for epic-1, True for epic-2
        with patch("gobby.workflows.task_enforcement_actions.is_descendant_of") as mock_descendant:
            mock_descendant.side_effect = [False, True]  # Not under epic-1, but under epic-2

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state,
                event_data=event_data,
            )

        assert result is None  # Allowed - descendant of epic-2
        assert mock_descendant.call_count == 2

    async def test_array_blocks_if_not_descendant_of_any(self, mock_task_manager):
        """When session_task is array, blocks if not descendant of any."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": ["epic-1", "epic-2"]},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "unrelated-task", "status": "in_progress"}},
        }

        with patch("gobby.workflows.task_enforcement_actions.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = False  # Not under any

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state,
                event_data=event_data,
            )

        assert result is not None
        assert result["decision"] == "block"
        assert "epic-1" in result["reason"]
        assert "epic-2" in result["reason"]

    async def test_empty_array_allows_all(self, mock_task_manager):
        """Empty session_task array means no scope restriction."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": []},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state,
            event_data=event_data,
        )

        assert result is None  # Allowed - empty list means no restriction
