"""
Comprehensive unit tests for uncovered action functions in actions.py.

This module targets specific uncovered lines to increase coverage:
- _handle_get_workflow_tasks (lines 483-519)
- _handle_skills_sync_export (lines 777-784)
- _handle_require_task_complete (lines 894-933)
- Stop signal actions
- Autonomous execution actions (progress tracking, stuck detection)
- Plugin action validation wrapper
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.templates import TemplateEngine

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_services():
    """Create mock service dependencies."""
    return {
        "template_engine": MagicMock(spec=TemplateEngine),
        "llm_service": AsyncMock(),
        "transcript_processor": MagicMock(),
        "config": MagicMock(),
        "mcp_manager": AsyncMock(),
        "memory_manager": MagicMock(),
        "task_manager": MagicMock(),
        "session_task_manager": MagicMock(),
        "stop_registry": MagicMock(),
        "progress_tracker": MagicMock(),
        "stuck_detector": MagicMock(),
        "websocket_server": MagicMock(),
    }


@pytest.fixture
def workflow_state():
    """Create a workflow state for testing."""
    return WorkflowState(
        session_id="test-session-id",
        workflow_name="test-workflow",
        step="test-step",
        step_entered_at=datetime.now(UTC),
        variables={},
    )


@pytest.fixture
def action_context(temp_db, session_manager, workflow_state, mock_services):
    """Create an action context for testing."""
    return ActionContext(
        session_id=workflow_state.session_id,
        state=workflow_state,
        db=temp_db,
        session_manager=session_manager,
        template_engine=mock_services["template_engine"],
        mcp_manager=mock_services["mcp_manager"],
        memory_manager=mock_services["memory_manager"],
    )


@pytest.fixture
def action_executor(temp_db, session_manager, mock_services):
    """Create an action executor with all mock services."""
    return ActionExecutor(
        db=temp_db,
        session_manager=session_manager,
        template_engine=mock_services["template_engine"],
        llm_service=mock_services["llm_service"],
        transcript_processor=mock_services["transcript_processor"],
        config=mock_services["config"],
        mcp_manager=mock_services["mcp_manager"],
        memory_manager=mock_services["memory_manager"],
        task_manager=mock_services["task_manager"],
        session_task_manager=mock_services["session_task_manager"],
        stop_registry=mock_services["stop_registry"],
        progress_tracker=mock_services["progress_tracker"],
        stuck_detector=mock_services["stuck_detector"],
        websocket_server=mock_services["websocket_server"],
    )


# =============================================================================
# Test _handle_get_workflow_tasks (lines 483-519)
# =============================================================================


class TestHandleGetWorkflowTasks:
    """Tests for _handle_get_workflow_tasks action."""

    @pytest.mark.asyncio
    async def test_get_workflow_tasks_with_workflow_name(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test getting tasks with explicit workflow name."""
        # Set workflow name in state
        action_context.state.workflow_name = "test-workflow"

        # Create a session so session lookup works
        session = session_manager.register(
            external_id="workflow-tasks-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        with patch("gobby.workflows.task_actions.get_workflow_tasks") as mock_get_tasks:
            mock_task = MagicMock()
            mock_task.id = "gt-123"
            mock_task.title = "Test Task"
            mock_task.status = "open"
            mock_task.to_dict.return_value = {
                "id": "gt-123",
                "title": "Test Task",
                "status": "open",
            }
            mock_get_tasks.return_value = [mock_task]

            result = await action_executor.execute(
                "get_workflow_tasks",
                action_context,
            )

            assert result is not None
            assert result["count"] == 1
            assert len(result["tasks"]) == 1
            assert result["tasks"][0]["id"] == "gt-123"

            # Verify task_list is updated in state
            assert action_context.state.task_list is not None
            assert len(action_context.state.task_list) == 1

    @pytest.mark.asyncio
    async def test_get_workflow_tasks_with_output_variable(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test storing tasks in a workflow variable."""
        action_context.state.workflow_name = "test-workflow"

        session = session_manager.register(
            external_id="workflow-tasks-var-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        with patch("gobby.workflows.task_actions.get_workflow_tasks") as mock_get_tasks:
            mock_task = MagicMock()
            mock_task.id = "gt-456"
            mock_task.title = "Stored Task"
            mock_task.status = "in_progress"
            mock_task.to_dict.return_value = {
                "id": "gt-456",
                "title": "Stored Task",
                "status": "in_progress",
            }
            mock_get_tasks.return_value = [mock_task]

            result = await action_executor.execute(
                "get_workflow_tasks",
                action_context,
                **{"as": "my_tasks"},
            )

            assert result["count"] == 1
            assert action_context.state.variables["my_tasks"] is not None
            assert len(action_context.state.variables["my_tasks"]) == 1

    @pytest.mark.asyncio
    async def test_get_workflow_tasks_no_workflow_name(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test error when no workflow name is specified."""
        action_context.state.workflow_name = None

        session = session_manager.register(
            external_id="no-workflow-name-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        result = await action_executor.execute(
            "get_workflow_tasks",
            action_context,
        )

        assert result is not None
        assert "error" in result
        assert "No workflow name" in result["error"]

    @pytest.mark.asyncio
    async def test_get_workflow_tasks_include_closed(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test including closed tasks."""
        action_context.state.workflow_name = "test-workflow"

        session = session_manager.register(
            external_id="include-closed-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        with patch("gobby.workflows.task_actions.get_workflow_tasks") as mock_get_tasks:
            mock_get_tasks.return_value = []

            await action_executor.execute(
                "get_workflow_tasks",
                action_context,
                include_closed=True,
            )

            # Verify include_closed was passed
            mock_get_tasks.assert_called_once()
            call_kwargs = mock_get_tasks.call_args.kwargs
            assert call_kwargs["include_closed"] is True

    @pytest.mark.asyncio
    async def test_get_workflow_tasks_with_override_workflow_name(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test overriding workflow name via kwargs."""
        action_context.state.workflow_name = "default-workflow"

        session = session_manager.register(
            external_id="override-workflow-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        with patch("gobby.workflows.task_actions.get_workflow_tasks") as mock_get_tasks:
            mock_get_tasks.return_value = []

            await action_executor.execute(
                "get_workflow_tasks",
                action_context,
                workflow_name="override-workflow",
            )

            # Verify overridden workflow name was used
            mock_get_tasks.assert_called_once()
            call_kwargs = mock_get_tasks.call_args.kwargs
            assert call_kwargs["workflow_name"] == "override-workflow"


# =============================================================================
# Test _handle_require_task_complete (lines 894-933)
# =============================================================================


class TestHandleRequireTaskComplete:
    """Tests for _handle_require_task_complete action."""

    @pytest.mark.asyncio
    async def test_require_task_complete_no_task_spec(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test when no task_id is specified - should return None (allow)."""
        session = session_manager.register(
            external_id="no-task-spec",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        result = await action_executor.execute(
            "require_task_complete",
            action_context,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_require_task_complete_wildcard_no_ready_tasks(
        self, action_executor, action_context, session_manager, sample_project, mock_services
    ):
        """Test wildcard mode with no ready tasks - should allow stop."""
        session = session_manager.register(
            external_id="wildcard-no-tasks",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        mock_services["task_manager"].list_ready_tasks.return_value = []

        result = await action_executor.execute(
            "require_task_complete",
            action_context,
            task_id="*",
        )

        assert result is None  # Allow stop

    @pytest.mark.asyncio
    async def test_require_task_complete_wildcard_with_ready_tasks(
        self, action_executor, action_context, session_manager, sample_project, mock_services
    ):
        """Test wildcard mode with ready tasks - should check completion."""
        session = session_manager.register(
            external_id="wildcard-with-tasks",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        mock_task = MagicMock()
        mock_task.id = "gt-ready-123"
        mock_services["task_manager"].list_ready_tasks.return_value = [mock_task]

        with patch("gobby.workflows.actions.require_task_complete") as mock_require:
            mock_require.return_value = {"decision": "block", "reason": "Task incomplete"}

            await action_executor.execute(
                "require_task_complete",
                action_context,
                task_id="*",
            )

            # Should have called require_task_complete with the ready task IDs
            mock_require.assert_called_once()
            call_kwargs = mock_require.call_args.kwargs
            assert "gt-ready-123" in call_kwargs["task_ids"]

    @pytest.mark.asyncio
    async def test_require_task_complete_list_of_tasks(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test with a list of task IDs."""
        session = session_manager.register(
            external_id="task-list-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        task_ids = ["gt-task1", "gt-task2", "gt-task3"]

        with patch("gobby.workflows.actions.require_task_complete") as mock_require:
            mock_require.return_value = None  # Allow

            await action_executor.execute(
                "require_task_complete",
                action_context,
                task_id=task_ids,
            )

            mock_require.assert_called_once()
            call_kwargs = mock_require.call_args.kwargs
            assert call_kwargs["task_ids"] == task_ids

    @pytest.mark.asyncio
    async def test_require_task_complete_single_task(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test with a single task ID string."""
        session = session_manager.register(
            external_id="single-task-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        with patch("gobby.workflows.actions.require_task_complete") as mock_require:
            mock_require.return_value = None

            await action_executor.execute(
                "require_task_complete",
                action_context,
                task_id="gt-single-task",
            )

            mock_require.assert_called_once()
            call_kwargs = mock_require.call_args.kwargs
            assert call_kwargs["task_ids"] == ["gt-single-task"]

    @pytest.mark.asyncio
    async def test_require_task_complete_template_resolution(
        self, action_executor, action_context, session_manager, sample_project, mock_services
    ):
        """Test template resolution for task_id."""
        session = session_manager.register(
            external_id="template-task-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id
        action_context.state.variables = {"session_task": "gt-resolved-task"}

        # Mock template engine to resolve the variable
        mock_services["template_engine"].render.return_value = "gt-resolved-task"

        with patch("gobby.workflows.actions.require_task_complete") as mock_require:
            mock_require.return_value = None

            await action_executor.execute(
                "require_task_complete",
                action_context,
                task_id="{{ variables.session_task }}",
            )

            # Verify template was rendered
            mock_services["template_engine"].render.assert_called()


# =============================================================================
# Test Stop Signal Actions
# =============================================================================


class TestStopSignalActions:
    """Tests for stop signal action handlers."""

    @pytest.mark.asyncio
    async def test_check_stop_signal_no_signal(
        self, action_executor, action_context, mock_services
    ):
        """Test check_stop_signal when no signal is pending."""
        mock_signal = MagicMock()
        mock_signal.is_pending = False
        mock_services["stop_registry"].get_signal.return_value = mock_signal

        result = await action_executor.execute(
            "check_stop_signal",
            action_context,
        )

        assert result["has_signal"] is False

    @pytest.mark.asyncio
    async def test_check_stop_signal_with_pending_signal(
        self, action_executor, action_context, mock_services
    ):
        """Test check_stop_signal with a pending signal."""
        mock_signal = MagicMock()
        mock_signal.is_pending = True
        mock_signal.source = "http"
        mock_signal.reason = "User requested stop"
        mock_signal.requested_at = datetime.now(UTC)
        mock_services["stop_registry"].get_signal.return_value = mock_signal

        result = await action_executor.execute(
            "check_stop_signal",
            action_context,
        )

        assert result["has_signal"] is True
        assert result["signal"]["source"] == "http"
        assert "inject_context" in result
        assert action_context.state.variables["_stop_signal_pending"] is True

    @pytest.mark.asyncio
    async def test_check_stop_signal_with_acknowledge(
        self, action_executor, action_context, mock_services
    ):
        """Test check_stop_signal with acknowledge=True."""
        mock_signal = MagicMock()
        mock_signal.is_pending = True
        mock_signal.source = "cli"
        mock_signal.reason = "Stopping"
        mock_signal.requested_at = datetime.now(UTC)
        mock_services["stop_registry"].get_signal.return_value = mock_signal

        result = await action_executor.execute(
            "check_stop_signal",
            action_context,
            acknowledge=True,
        )

        assert result["acknowledged"] is True
        mock_services["stop_registry"].acknowledge.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_stop_signal_no_registry(self, action_executor, action_context):
        """Test check_stop_signal when stop_registry is None."""
        action_executor.stop_registry = None

        result = await action_executor.execute(
            "check_stop_signal",
            action_context,
        )

        assert result["has_signal"] is False

    @pytest.mark.asyncio
    async def test_request_stop(self, action_executor, action_context, mock_services):
        """Test request_stop action."""
        mock_signal = MagicMock()
        mock_signal.session_id = "test-session-id"
        mock_signal.source = "workflow"
        mock_signal.reason = "Test reason"
        mock_signal.requested_at = datetime.now(UTC)
        mock_services["stop_registry"].signal_stop.return_value = mock_signal

        result = await action_executor.execute(
            "request_stop",
            action_context,
            reason="Test reason",
        )

        assert result["success"] is True
        assert result["signal"]["source"] == "workflow"
        mock_services["stop_registry"].signal_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_stop_no_registry(self, action_executor, action_context):
        """Test request_stop when stop_registry is None."""
        action_executor.stop_registry = None

        result = await action_executor.execute(
            "request_stop",
            action_context,
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_clear_stop_signal(self, action_executor, action_context, mock_services):
        """Test clear_stop_signal action."""
        mock_services["stop_registry"].clear.return_value = True

        result = await action_executor.execute(
            "clear_stop_signal",
            action_context,
        )

        assert result["success"] is True
        assert result["cleared"] is True

    @pytest.mark.asyncio
    async def test_clear_stop_signal_target_session(
        self, action_executor, action_context, mock_services
    ):
        """Test clear_stop_signal for a different session."""
        mock_services["stop_registry"].clear.return_value = True

        await action_executor.execute(
            "clear_stop_signal",
            action_context,
            session_id="other-session-id",
        )

        mock_services["stop_registry"].clear.assert_called_with("other-session-id")


# =============================================================================
# Test Autonomous Execution Actions
# =============================================================================


class TestAutonomousExecutionActions:
    """Tests for autonomous execution action handlers."""

    @pytest.mark.asyncio
    async def test_start_progress_tracking(self, action_executor, action_context, mock_services):
        """Test start_progress_tracking action."""
        result = await action_executor.execute(
            "start_progress_tracking",
            action_context,
        )

        assert result["success"] is True
        assert action_context.state.variables["_progress_tracking_active"] is True
        mock_services["progress_tracker"].clear_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_progress_tracking_no_tracker(self, action_executor, action_context):
        """Test start_progress_tracking when tracker is None."""
        action_executor.progress_tracker = None

        result = await action_executor.execute(
            "start_progress_tracking",
            action_context,
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_stop_progress_tracking(self, action_executor, action_context, mock_services):
        """Test stop_progress_tracking action."""
        mock_summary = MagicMock()
        mock_summary.total_events = 10
        mock_summary.high_value_events = 3
        mock_summary.is_stagnant = False
        mock_services["progress_tracker"].get_summary.return_value = mock_summary

        result = await action_executor.execute(
            "stop_progress_tracking",
            action_context,
        )

        assert result["success"] is True
        assert result["final_summary"]["total_events"] == 10
        assert action_context.state.variables["_progress_tracking_active"] is False

    @pytest.mark.asyncio
    async def test_stop_progress_tracking_keep_data(
        self, action_executor, action_context, mock_services
    ):
        """Test stop_progress_tracking with keep_data=True."""
        # Reset the mock to ensure isolation from other tests
        mock_services["progress_tracker"].reset_mock()

        mock_summary = MagicMock()
        mock_summary.total_events = 5
        mock_summary.high_value_events = 2
        mock_summary.is_stagnant = False
        mock_services["progress_tracker"].get_summary.return_value = mock_summary

        result = await action_executor.execute(
            "stop_progress_tracking",
            action_context,
            keep_data=True,
        )

        assert result["success"] is True
        # clear_session should NOT be called when keep_data is True
        mock_services["progress_tracker"].clear_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_progress(self, action_executor, action_context, mock_services):
        """Test record_progress action."""
        mock_event = MagicMock()
        mock_event.progress_type.value = "tool_call"
        mock_event.is_high_value = True
        mock_event.timestamp = datetime.now(UTC)
        mock_services["progress_tracker"].record_event.return_value = mock_event

        result = await action_executor.execute(
            "record_progress",
            action_context,
            progress_type="tool_call",
            tool_name="Edit",
        )

        assert result["success"] is True
        assert result["event"]["is_high_value"] is True

    @pytest.mark.asyncio
    async def test_record_progress_string_type_conversion(
        self, action_executor, action_context, mock_services
    ):
        """Test record_progress with string progress_type that needs conversion."""
        mock_event = MagicMock()
        mock_event.progress_type.value = "file_change"
        mock_event.is_high_value = True
        mock_event.timestamp = datetime.now(UTC)
        mock_services["progress_tracker"].record_event.return_value = mock_event

        result = await action_executor.execute(
            "record_progress",
            action_context,
            progress_type="file_change",
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_detect_task_loop(self, action_executor, action_context, mock_services):
        """Test detect_task_loop action."""
        mock_result = MagicMock()
        mock_result.is_stuck = True
        mock_result.reason = "Repeated task selections"
        mock_result.layer = "task_loop"
        mock_result.details = {"task_id": "gt-123"}
        mock_result.suggested_action = "Choose a different task"
        mock_services["stuck_detector"].detect_task_loop.return_value = mock_result

        result = await action_executor.execute(
            "detect_task_loop",
            action_context,
        )

        assert result["is_stuck"] is True
        assert result["layer"] == "task_loop"
        assert action_context.state.variables["_task_loop_detected"] is True
        assert action_context.state.variables["_task_loop_task_id"] == "gt-123"

    @pytest.mark.asyncio
    async def test_detect_task_loop_not_stuck(self, action_executor, action_context, mock_services):
        """Test detect_task_loop when not stuck."""
        mock_result = MagicMock()
        mock_result.is_stuck = False
        mock_result.reason = None
        mock_result.layer = None
        mock_result.details = None
        mock_result.suggested_action = None
        mock_services["stuck_detector"].detect_task_loop.return_value = mock_result

        result = await action_executor.execute(
            "detect_task_loop",
            action_context,
        )

        assert result["is_stuck"] is False
        assert action_context.state.variables["_task_loop_detected"] is False

    @pytest.mark.asyncio
    async def test_detect_stuck(self, action_executor, action_context, mock_services):
        """Test detect_stuck action (full detection)."""
        mock_result = MagicMock()
        mock_result.is_stuck = True
        mock_result.reason = "No progress in 10 minutes"
        mock_result.layer = "progress"
        mock_result.details = {}
        mock_result.suggested_action = "Consider stopping"
        mock_services["stuck_detector"].is_stuck.return_value = mock_result

        result = await action_executor.execute(
            "detect_stuck",
            action_context,
        )

        assert result["is_stuck"] is True
        assert "inject_context" in result
        assert "Stuck Detected" in result["inject_context"]
        assert action_context.state.variables["_is_stuck"] is True

    @pytest.mark.asyncio
    async def test_detect_stuck_not_stuck(self, action_executor, action_context, mock_services):
        """Test detect_stuck when not stuck."""
        mock_result = MagicMock()
        mock_result.is_stuck = False
        mock_result.reason = None
        mock_result.layer = None
        mock_result.details = None
        mock_result.suggested_action = None
        mock_services["stuck_detector"].is_stuck.return_value = mock_result

        result = await action_executor.execute(
            "detect_stuck",
            action_context,
        )

        assert result["is_stuck"] is False
        assert "inject_context" not in result

    @pytest.mark.asyncio
    async def test_record_task_selection(self, action_executor, action_context, mock_services):
        """Test record_task_selection action."""
        mock_event = MagicMock()
        mock_event.task_id = "gt-selected"
        mock_event.selected_at = datetime.now(UTC)
        mock_services["stuck_detector"].record_task_selection.return_value = mock_event

        result = await action_executor.execute(
            "record_task_selection",
            action_context,
            task_id="gt-selected",
        )

        assert result["success"] is True
        assert result["task_id"] == "gt-selected"

    @pytest.mark.asyncio
    async def test_record_task_selection_with_selection_context(
        self, temp_db, session_manager, mock_services
    ):
        """Test record_task_selection with selection context.

        This test uses a custom action_context to avoid the `context` kwarg conflict
        with ActionExecutor.execute(context=ActionContext).
        """
        from gobby.workflows.autonomous_actions import record_task_selection

        mock_event = MagicMock()
        mock_event.task_id = "gt-with-context"
        mock_event.selected_at = datetime.now(UTC)
        mock_stuck_detector = MagicMock()
        mock_stuck_detector.record_task_selection.return_value = mock_event

        # Call the underlying function directly to test context passing
        result = record_task_selection(
            stuck_detector=mock_stuck_detector,
            session_id="test-session-id",
            task_id="gt-with-context",
            context={"reason": "First available task"},
        )

        assert result["success"] is True
        mock_stuck_detector.record_task_selection.assert_called_with(
            session_id="test-session-id",
            task_id="gt-with-context",
            context={"reason": "First available task"},
        )

    @pytest.mark.asyncio
    async def test_get_progress_summary(self, action_executor, action_context, mock_services):
        """Test get_progress_summary action."""
        from gobby.autonomous.progress_tracker import ProgressType

        mock_summary = MagicMock()
        mock_summary.total_events = 25
        mock_summary.high_value_events = 8
        mock_summary.is_stagnant = False
        mock_summary.stagnation_duration_seconds = 0
        mock_summary.last_high_value_at = datetime.now(UTC)
        mock_summary.last_event_at = datetime.now(UTC)
        mock_summary.events_by_type = {ProgressType.TOOL_CALL: 20, ProgressType.FILE_MODIFIED: 5}
        mock_services["progress_tracker"].get_summary.return_value = mock_summary

        result = await action_executor.execute(
            "get_progress_summary",
            action_context,
        )

        assert result["total_events"] == 25
        assert result["high_value_events"] == 8
        assert result["is_stagnant"] is False
        assert "events_by_type" in result

    @pytest.mark.asyncio
    async def test_get_progress_summary_no_tracker(self, action_executor, action_context):
        """Test get_progress_summary when tracker is None."""
        action_executor.progress_tracker = None

        result = await action_executor.execute(
            "get_progress_summary",
            action_context,
        )

        assert "error" in result


# =============================================================================
# Test Plugin Action Validation Wrapper
# =============================================================================


class TestPluginActionValidationWrapper:
    """Tests for the plugin action validation wrapper."""

    @pytest.fixture
    def mock_plugin_action(self):
        """Create a mock plugin action with schema."""
        action = MagicMock()
        action.name = "test_action"
        action.schema = {"type": "object", "properties": {"param": {"type": "string"}}}
        action.handler = AsyncMock(return_value={"result": "success"})
        return action

    def test_create_validating_wrapper(self, action_executor, mock_plugin_action):
        """Test that validating wrapper is created correctly."""
        wrapper = action_executor._create_validating_wrapper(mock_plugin_action)
        assert callable(wrapper)

    @pytest.mark.asyncio
    async def test_validating_wrapper_passes_valid_input(
        self, action_executor, action_context, mock_plugin_action
    ):
        """Test wrapper passes valid input to handler."""
        mock_plugin_action.validate_input.return_value = (True, None)
        wrapper = action_executor._create_validating_wrapper(mock_plugin_action)

        result = await wrapper(action_context, param="test_value")

        assert result == {"result": "success"}
        mock_plugin_action.handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_validating_wrapper_rejects_invalid_input(
        self, action_executor, action_context, mock_plugin_action
    ):
        """Test wrapper rejects invalid input."""
        mock_plugin_action.validate_input.return_value = (False, "param is required")
        wrapper = action_executor._create_validating_wrapper(mock_plugin_action)

        result = await wrapper(action_context)

        assert "error" in result
        assert "param is required" in result["error"]
        mock_plugin_action.handler.assert_not_called()


# =============================================================================
# Test Broadcast Autonomous Event
# =============================================================================


class TestBroadcastAutonomousEvent:
    """Tests for _broadcast_autonomous_event helper."""

    @pytest.mark.asyncio
    async def test_broadcast_autonomous_event_success(self, action_executor, mock_services):
        """Test successful broadcast of autonomous event."""
        mock_services["websocket_server"].broadcast_autonomous_event = AsyncMock()

        await action_executor._broadcast_autonomous_event(
            event="task_started",
            session_id="test-session",
            task_id="gt-123",
        )

        # Give the async task time to execute
        import asyncio

        await asyncio.sleep(0.01)

        # The broadcast should have been scheduled

    @pytest.mark.asyncio
    async def test_broadcast_autonomous_event_no_server(self, action_executor):
        """Test broadcast when websocket_server is None."""
        action_executor.websocket_server = None

        # Should not raise
        await action_executor._broadcast_autonomous_event(
            event="task_started",
            session_id="test-session",
        )


# =============================================================================
# Test Register Plugin Actions
# =============================================================================


class TestRegisterPluginActions:
    """Tests for register_plugin_actions method."""

    def test_register_plugin_actions_none_registry(self, action_executor):
        """Test register_plugin_actions with None registry."""
        # Should not raise
        action_executor.register_plugin_actions(None)

    def test_register_plugin_actions_with_schema(self, action_executor):
        """Test registering plugin actions that have schemas."""
        mock_registry = MagicMock()
        mock_plugin = MagicMock()
        mock_plugin._actions = {}

        mock_action = MagicMock()
        mock_action.schema = {"type": "object"}
        mock_action.handler = AsyncMock()
        mock_plugin._actions["validated_action"] = mock_action

        mock_registry._plugins = {"test-plugin": mock_plugin}

        action_executor.register_plugin_actions(mock_registry)

        # Verify action was registered with full name
        assert "plugin:test-plugin:validated_action" in action_executor._handlers

    def test_register_plugin_actions_without_schema(self, action_executor):
        """Test registering plugin actions without schemas."""
        mock_registry = MagicMock()
        mock_plugin = MagicMock()
        mock_plugin._actions = {}

        mock_action = MagicMock()
        mock_action.schema = None  # No schema
        mock_action.handler = AsyncMock()
        mock_plugin._actions["simple_action"] = mock_action

        mock_registry._plugins = {"test-plugin": mock_plugin}

        action_executor.register_plugin_actions(mock_registry)

        # Verify action was registered directly (no wrapper)
        assert "plugin:test-plugin:simple_action" in action_executor._handlers


# =============================================================================
# Test Update Workflow Task
# =============================================================================


class TestHandleUpdateWorkflowTask:
    """Tests for _handle_update_workflow_task action."""

    @pytest.mark.asyncio
    async def test_update_workflow_task_with_task_id(self, action_executor, action_context):
        """Test updating a task with explicit task_id."""
        with patch("gobby.workflows.task_actions.update_task_from_workflow") as mock_update:
            mock_task = MagicMock()
            mock_task.to_dict.return_value = {"id": "gt-123", "status": "closed"}
            mock_update.return_value = mock_task

            result = await action_executor.execute(
                "update_workflow_task",
                action_context,
                task_id="gt-123",
                status="closed",
            )

            assert result["updated"] is True
            assert result["task"]["status"] == "closed"

    @pytest.mark.asyncio
    async def test_update_workflow_task_from_current_index(self, action_executor, action_context):
        """Test updating task using current_task_index from state."""
        action_context.state.task_list = [
            {"id": "gt-first"},
            {"id": "gt-second"},
            {"id": "gt-third"},
        ]
        action_context.state.current_task_index = 1

        with patch("gobby.workflows.task_actions.update_task_from_workflow") as mock_update:
            mock_task = MagicMock()
            mock_task.to_dict.return_value = {"id": "gt-second", "status": "in_progress"}
            mock_update.return_value = mock_task

            result = await action_executor.execute(
                "update_workflow_task",
                action_context,
                status="in_progress",
            )

            assert result["updated"] is True
            # Verify the correct task was updated (gt-second at index 1)
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs["task_id"] == "gt-second"

    @pytest.mark.asyncio
    async def test_update_workflow_task_no_task_id(self, action_executor, action_context):
        """Test error when no task_id can be determined."""
        action_context.state.task_list = None
        action_context.state.current_task_index = None

        result = await action_executor.execute(
            "update_workflow_task",
            action_context,
            status="closed",
        )

        assert "error" in result
        assert "No task_id" in result["error"]

    @pytest.mark.asyncio
    async def test_update_workflow_task_not_found(self, action_executor, action_context):
        """Test when task is not found."""
        with patch("gobby.workflows.task_actions.update_task_from_workflow") as mock_update:
            mock_update.return_value = None

            result = await action_executor.execute(
                "update_workflow_task",
                action_context,
                task_id="gt-nonexistent",
                status="closed",
            )

            assert result["updated"] is False
            assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_update_workflow_task_with_validation_fields(
        self, action_executor, action_context
    ):
        """Test updating task with validation fields."""
        with patch("gobby.workflows.task_actions.update_task_from_workflow") as mock_update:
            mock_task = MagicMock()
            mock_task.to_dict.return_value = {
                "id": "gt-123",
                "validation_status": "valid",
                "validation_feedback": "All tests pass",
            }
            mock_update.return_value = mock_task

            result = await action_executor.execute(
                "update_workflow_task",
                action_context,
                task_id="gt-123",
                validation_status="valid",
                validation_feedback="All tests pass",
            )

            assert result["updated"] is True
            mock_update.assert_called_with(
                db=action_context.db,
                task_id="gt-123",
                status=None,
                verification=None,
                validation_status="valid",
                validation_feedback="All tests pass",
            )


# =============================================================================
# Test Persist Tasks Action
# =============================================================================


class TestHandlePersistTasks:
    """Tests for _handle_persist_tasks action."""

    @pytest.mark.asyncio
    async def test_persist_tasks_no_tasks(self, action_executor, action_context):
        """Test persist_tasks when no tasks provided."""
        result = await action_executor.execute(
            "persist_tasks",
            action_context,
        )

        assert result["tasks_persisted"] == 0
        assert result["ids"] == []

    @pytest.mark.asyncio
    async def test_persist_tasks_from_tasks_kwarg(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test persist_tasks from direct tasks kwarg."""
        session = session_manager.register(
            external_id="persist-tasks-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        with patch("gobby.workflows.task_actions.persist_decomposed_tasks") as mock_persist:
            mock_persist.return_value = {"1": "gt-persisted-1", "2": "gt-persisted-2"}

            result = await action_executor.execute(
                "persist_tasks",
                action_context,
                tasks=[
                    {"id": "1", "title": "Task 1"},
                    {"id": "2", "title": "Task 2"},
                ],
            )

            assert result["tasks_persisted"] == 2
            assert "gt-persisted-1" in result["ids"]
            assert "gt-persisted-2" in result["ids"]

    @pytest.mark.asyncio
    async def test_persist_tasks_from_source_variable(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test persist_tasks using source variable."""
        session = session_manager.register(
            external_id="persist-source-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        # Store tasks in a workflow variable
        action_context.state.variables = {
            "task_plan": [
                {"id": "1", "title": "Plan Task 1"},
            ]
        }

        with patch("gobby.workflows.task_actions.persist_decomposed_tasks") as mock_persist:
            mock_persist.return_value = {"1": "gt-plan-1"}

            result = await action_executor.execute(
                "persist_tasks",
                action_context,
                source="task_plan",
            )

            assert result["tasks_persisted"] == 1

    @pytest.mark.asyncio
    async def test_persist_tasks_from_nested_dict_source(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test persist_tasks using nested dict with tasks key."""
        session = session_manager.register(
            external_id="persist-nested-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        # Store tasks in a nested structure
        action_context.state.variables = {
            "task_list": {
                "tasks": [
                    {"id": "1", "title": "Nested Task 1"},
                ],
                "metadata": {"count": 1},
            }
        }

        with patch("gobby.workflows.task_actions.persist_decomposed_tasks") as mock_persist:
            mock_persist.return_value = {"1": "gt-nested-1"}

            result = await action_executor.execute(
                "persist_tasks",
                action_context,
                source="task_list",
            )

            assert result["tasks_persisted"] == 1

    @pytest.mark.asyncio
    async def test_persist_tasks_exception_handling(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test persist_tasks handles exceptions gracefully."""
        session = session_manager.register(
            external_id="persist-error-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        with patch("gobby.workflows.task_actions.persist_decomposed_tasks") as mock_persist:
            mock_persist.side_effect = ValueError("Invalid task data")

            result = await action_executor.execute(
                "persist_tasks",
                action_context,
                tasks=[{"id": "1", "title": "Bad Task"}],
            )

            assert "error" in result
            assert "Invalid task data" in result["error"]


# =============================================================================
# Test Require Active Task Action
# =============================================================================


class TestHandleRequireActiveTask:
    """Tests for _handle_require_active_task action."""

    @pytest.mark.asyncio
    async def test_require_active_task_delegated(
        self, action_executor, action_context, session_manager, sample_project
    ):
        """Test require_active_task delegates to the action function."""
        session = session_manager.register(
            external_id="require-active-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
        )
        action_context.session_id = session.id

        with patch("gobby.workflows.actions.require_active_task") as mock_require:
            mock_require.return_value = None  # Allow

            await action_executor.execute(
                "require_active_task",
                action_context,
            )

            mock_require.assert_called_once()
            call_kwargs = mock_require.call_args.kwargs
            assert call_kwargs["session_id"] == session.id


# =============================================================================
# Test Require Commit Before Stop Action
# =============================================================================


class TestHandleRequireCommitBeforeStop:
    """Tests for _handle_require_commit_before_stop action."""

    @pytest.mark.asyncio
    async def test_require_commit_before_stop_with_cwd(self, action_executor, action_context):
        """Test require_commit_before_stop extracts cwd from event_data."""
        action_context.event_data = {"cwd": "/path/to/project"}

        with patch("gobby.workflows.actions.require_commit_before_stop") as mock_require:
            mock_require.return_value = None

            await action_executor.execute(
                "require_commit_before_stop",
                action_context,
            )

            mock_require.assert_called_once()
            call_kwargs = mock_require.call_args.kwargs
            assert call_kwargs["project_path"] == "/path/to/project"

    @pytest.mark.asyncio
    async def test_require_commit_before_stop_no_event_data(self, action_executor, action_context):
        """Test require_commit_before_stop handles missing event_data."""
        action_context.event_data = None

        with patch("gobby.workflows.actions.require_commit_before_stop") as mock_require:
            mock_require.return_value = None

            await action_executor.execute(
                "require_commit_before_stop",
                action_context,
            )

            mock_require.assert_called_once()
            call_kwargs = mock_require.call_args.kwargs
            assert call_kwargs["project_path"] is None


# =============================================================================
# Test Validate Session Task Scope Action
# =============================================================================


class TestHandleValidateSessionTaskScope:
    """Tests for _handle_validate_session_task_scope action."""

    @pytest.mark.asyncio
    async def test_validate_session_task_scope_delegated(self, action_executor, action_context):
        """Test validate_session_task_scope delegates correctly."""
        with patch("gobby.workflows.actions.validate_session_task_scope") as mock_validate:
            mock_validate.return_value = None

            await action_executor.execute(
                "validate_session_task_scope",
                action_context,
            )

            mock_validate.assert_called_once()


# =============================================================================
# Test Webhook Action
# =============================================================================


class TestHandleWebhook:
    """Tests for _handle_webhook action."""

    @pytest.mark.asyncio
    async def test_webhook_missing_url_and_id(self, action_executor, action_context):
        """Test webhook returns error when neither url nor webhook_id provided."""
        result = await action_executor.execute(
            "webhook",
            action_context,
            method="POST",
        )

        assert result["success"] is False
        assert "Either url or webhook_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_webhook_invalid_config(self, action_executor, action_context):
        """Test webhook handles invalid config gracefully."""
        result = await action_executor.execute(
            "webhook",
            action_context,
            url="not-a-valid-url",  # Invalid URL
            method="INVALID_METHOD",
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_webhook_with_capture_response(
        self, action_executor, action_context, mock_services
    ):
        """Test webhook captures response into variables."""
        from gobby.workflows.webhook_executor import WebhookResult

        # Mock the executor
        with patch("gobby.workflows.actions.WebhookExecutor") as mock_executor_class:
            mock_executor = MagicMock()
            mock_result = WebhookResult(
                success=True,
                status_code=200,
                body='{"key": "value"}',
                headers={"Content-Type": "application/json"},
            )
            mock_executor.execute = AsyncMock(return_value=mock_result)
            mock_executor_class.return_value = mock_executor

            result = await action_executor.execute(
                "webhook",
                action_context,
                url="https://example.com/api",
                method="GET",
                capture_response={
                    "status_var": "response_status",
                    "body_var": "response_body",
                    "headers_var": "response_headers",
                },
            )

            assert result["success"] is True
            assert result["status_code"] == 200
            # Verify variables were captured
            assert action_context.state.variables["response_status"] == 200
            assert action_context.state.variables["response_body"] == {"key": "value"}
            assert "response_headers" in action_context.state.variables

    @pytest.mark.asyncio
    async def test_webhook_with_webhook_id_unsupported(self, action_executor, action_context):
        """Test webhook_id returns error (not yet supported)."""
        result = await action_executor.execute(
            "webhook",
            action_context,
            webhook_id="my-webhook",
        )

        assert result["success"] is False
        assert "webhook_id requires" in result["error"]


# =============================================================================
# Test Mark Loop Complete
# =============================================================================


class TestHandleMarkLoopComplete:
    """Tests for _handle_mark_loop_complete action."""

    @pytest.mark.asyncio
    async def test_mark_loop_complete(self, action_executor, action_context):
        """Test mark_loop_complete delegates to mark_loop_complete function."""
        with patch("gobby.workflows.actions.mark_loop_complete") as mock_mark:
            mock_mark.return_value = {"_loop_complete": True, "stop_reason": "completed"}

            result = await action_executor.execute(
                "mark_loop_complete",
                action_context,
            )

            mock_mark.assert_called_once()
            assert result is not None


# =============================================================================
# Test Extract Handoff Context Action
# =============================================================================


class TestHandleExtractHandoffContext:
    """Tests for _handle_extract_handoff_context action."""

    @pytest.mark.asyncio
    async def test_extract_handoff_context_delegated(self, action_executor, action_context):
        """Test extract_handoff_context delegates correctly."""
        with patch("gobby.workflows.actions.extract_handoff_context") as mock_extract:
            mock_extract.return_value = {"extracted": True}

            await action_executor.execute(
                "extract_handoff_context",
                action_context,
            )

            mock_extract.assert_called_once()


# =============================================================================
# Test Generate Handoff Compact Mode
# =============================================================================


class TestGenerateHandoffCompactMode:
    """Tests for generate_handoff action compact mode handling."""

    @pytest.mark.asyncio
    async def test_generate_handoff_compact_mode_fetches_previous_summary(
        self,
        action_executor,
        action_context,
        session_manager,
        sample_project,
        mock_services,
        tmp_path,
    ):
        """Test that compact mode fetches previous summary for cumulative compression."""
        import json

        # Create transcript file
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"role": "user", "content": "test"}) + "\n")

        # Create session with existing summary
        session = session_manager.register(
            external_id="compact-test",
            machine_id="test-machine",
            source="test-source",
            project_id=sample_project["id"],
            jsonl_path=str(transcript_file),
        )
        session_manager.update_summary(session.id, summary_markdown="Previous summary content")
        action_context.session_id = session.id

        # Set up event data indicating compact mode
        action_context.event_data = {"event_type": "pre_compact"}

        # Mock the services
        mock_services["transcript_processor"].extract_turns_since_clear.return_value = []
        mock_services["template_engine"].render.return_value = "Summarize prompt"

        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(return_value="New summary")
        mock_services["llm_service"].get_default_provider.return_value = mock_provider

        action_context.llm_service = mock_services["llm_service"]
        action_context.transcript_processor = mock_services["transcript_processor"]
        action_context.template_engine = mock_services["template_engine"]

        with patch("gobby.workflows.actions.generate_handoff") as mock_handoff:
            mock_handoff.return_value = {"handoff_created": True}

            await action_executor.execute(
                "generate_handoff",
                action_context,
            )

            # Verify mode="compact" and previous_summary were passed
            mock_handoff.assert_called_once()
            call_kwargs = mock_handoff.call_args.kwargs
            assert call_kwargs.get("mode") == "compact"
            assert call_kwargs.get("previous_summary") == "Previous summary content"


# =============================================================================
# Test ActionExecutor TextCompressor Integration
# =============================================================================


class TestActionExecutorCompressor:
    """Tests for ActionExecutor TextCompressor integration."""

    def test_compressor_created_when_config_has_compression(
        self, temp_db, session_manager, mock_services
    ):
        """Test that TextCompressor is created when config has compression settings."""
        from gobby.compression import CompressionConfig

        # Create a mock config with compression attribute
        mock_config = MagicMock()
        mock_config.compression = CompressionConfig(enabled=True)

        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            config=mock_config,
        )

        assert executor._compressor is not None
        assert executor._compressor.config.enabled is True

    def test_compressor_not_created_when_config_is_none(
        self, temp_db, session_manager, mock_services
    ):
        """Test that TextCompressor is not created when config is None."""
        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            config=None,
        )

        assert executor._compressor is None

    def test_compressor_not_created_when_config_has_no_compression(
        self, temp_db, session_manager, mock_services
    ):
        """Test that TextCompressor is not created when config has no compression attr."""
        # Create a mock config without compression attribute
        mock_config = MagicMock(spec=[])  # Empty spec = no attributes

        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            config=mock_config,
        )

        assert executor._compressor is None

    @pytest.mark.asyncio
    async def test_generate_summary_passes_compressor(
        self, temp_db, session_manager, mock_services, workflow_state
    ):
        """Test that _handle_generate_summary passes self._compressor to generate_summary."""
        from gobby.compression import CompressionConfig

        # Create executor with compression enabled
        mock_config = MagicMock()
        mock_config.compression = CompressionConfig(enabled=True)

        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            config=mock_config,
            llm_service=mock_services["llm_service"],
            transcript_processor=mock_services["transcript_processor"],
        )

        # Create action context
        context = ActionContext(
            session_id=workflow_state.session_id,
            state=workflow_state,
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            llm_service=mock_services["llm_service"],
            transcript_processor=mock_services["transcript_processor"],
        )

        with patch("gobby.workflows.actions.generate_summary") as mock_gen:
            mock_gen.return_value = {"summary_generated": True}

            await executor.execute("generate_summary", context)

            mock_gen.assert_called_once()
            call_kwargs = mock_gen.call_args.kwargs
            assert "compressor" in call_kwargs
            assert call_kwargs["compressor"] is executor._compressor

    @pytest.mark.asyncio
    async def test_generate_handoff_passes_compressor(
        self, temp_db, session_manager, mock_services, workflow_state
    ):
        """Test that _handle_generate_handoff passes self._compressor to generate_handoff."""
        from gobby.compression import CompressionConfig

        # Create executor with compression enabled
        mock_config = MagicMock()
        mock_config.compression = CompressionConfig(enabled=True)

        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            config=mock_config,
            llm_service=mock_services["llm_service"],
            transcript_processor=mock_services["transcript_processor"],
        )

        # Create action context
        context = ActionContext(
            session_id=workflow_state.session_id,
            state=workflow_state,
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            llm_service=mock_services["llm_service"],
            transcript_processor=mock_services["transcript_processor"],
        )

        with patch("gobby.workflows.actions.generate_handoff") as mock_gen:
            mock_gen.return_value = {"handoff_generated": True}

            await executor.execute("generate_handoff", context)

            mock_gen.assert_called_once()
            call_kwargs = mock_gen.call_args.kwargs
            assert "compressor" in call_kwargs
            assert call_kwargs["compressor"] is executor._compressor

    @pytest.mark.asyncio
    async def test_extract_handoff_context_passes_compressor(
        self, temp_db, session_manager, mock_services, workflow_state
    ):
        """Test that _handle_extract_handoff_context passes self._compressor."""
        from gobby.compression import CompressionConfig

        # Create executor with compression enabled
        mock_config = MagicMock()
        mock_config.compression = CompressionConfig(enabled=True)

        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            config=mock_config,
        )

        # Create action context
        context = ActionContext(
            session_id=workflow_state.session_id,
            state=workflow_state,
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            config=mock_config,
        )

        with patch("gobby.workflows.actions.extract_handoff_context") as mock_extract:
            mock_extract.return_value = {"handoff_context_extracted": True}

            await executor.execute("extract_handoff_context", context)

            mock_extract.assert_called_once()
            call_kwargs = mock_extract.call_args.kwargs
            assert "compressor" in call_kwargs
            assert call_kwargs["compressor"] is executor._compressor
            # Also verify db is passed
            assert "db" in call_kwargs
            assert call_kwargs["db"] is temp_db
