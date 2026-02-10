"""Tests for workflow detection helper functions."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.detection_helpers import (
    detect_mcp_call,
    detect_plan_mode_from_context,
    detect_task_claim,
    handle_detect_plan_mode_from_context,
    process_mcp_handlers,
)

pytestmark = pytest.mark.unit


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


@pytest.fixture
def mock_task_manager():
    """Mock LocalTaskManager."""
    mock = MagicMock()
    # Mock get_task to return a task with a UUID
    mock_task = MagicMock()
    mock_task.id = "task-uuid-123"
    mock.get_task.return_value = mock_task
    return mock


@pytest.fixture
def make_after_tool_event():
    """Factory for creating AFTER_TOOL events.

    Includes normalized fields that adapters would add:
    - mcp_server/mcp_tool: Extracted from tool_input.server_name/tool_name for MCP calls
    - tool_output: Normalized from tool_result/tool_response
    """

    def _make(tool_name: str, tool_input: dict | None = None, tool_output: dict | None = None):
        data = {
            "tool_name": tool_name,
            "tool_input": tool_input or {},
            "tool_output": tool_output or {},
        }

        # Simulate adapter normalization for MCP calls
        # Adapters extract these from CLI-specific formats
        if tool_name in ("call_tool", "mcp__gobby__call_tool") and tool_input:
            data["mcp_server"] = tool_input.get("server_name")
            data["mcp_tool"] = tool_input.get("tool_name")

        return HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            source=SessionSource.CLAUDE,
            session_id="test-session-ext",
            timestamp=datetime.now(UTC),
            data=data,
            metadata={"_platform_session_id": "test-session"},
        )

    return _make


@pytest.fixture
def make_before_agent_event():
    """Factory for creating BEFORE_AGENT events."""

    def _make(prompt: str):
        return HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            source=SessionSource.CLAUDE,
            session_id="test-session-ext",
            timestamp=datetime.now(UTC),
            data={"prompt": prompt},
            metadata={"_platform_session_id": "test-session"},
        )

    return _make


# =============================================================================
# Tests for detect_plan_mode_from_context (system reminder detection)
# =============================================================================


class TestDetectPlanModeFromContext:
    """Tests for detect_plan_mode_from_context function (prompt, state signature)."""

    def test_detects_plan_mode_active_indicator(self, workflow_state) -> None:
        """Detects 'Plan mode is active' in prompt."""
        prompt = "User prompt here\n<system-reminder>Plan mode is active</system-reminder>"

        detect_plan_mode_from_context(prompt, workflow_state)

        assert workflow_state.variables.get("plan_mode") is True

    def test_detects_plan_mode_still_active(self, workflow_state) -> None:
        """Detects 'Plan mode still active' in prompt."""
        prompt = "<system-reminder>Plan mode still active</system-reminder>\nWhat should I do?"

        detect_plan_mode_from_context(prompt, workflow_state)

        assert workflow_state.variables.get("plan_mode") is True

    def test_detects_you_are_in_plan_mode(self, workflow_state) -> None:
        """Detects 'You are in plan mode' in prompt."""
        prompt = "<system-reminder>You are in plan mode</system-reminder>. Please continue planning."

        detect_plan_mode_from_context(prompt, workflow_state)

        assert workflow_state.variables.get("plan_mode") is True

    def test_detects_exited_plan_mode(self, workflow_state) -> None:
        """Detects 'Exited Plan Mode' in prompt."""
        workflow_state.variables["plan_mode"] = True
        prompt = "<system-reminder>Exited Plan Mode</system-reminder>. Now implement the changes."

        detect_plan_mode_from_context(prompt, workflow_state)

        assert workflow_state.variables.get("plan_mode") is False

    def test_does_not_change_when_already_in_plan_mode(self, workflow_state) -> None:
        """Does not log again if already in plan mode."""
        workflow_state.variables["plan_mode"] = True
        prompt = "Plan mode is active"

        # Should not raise or change state
        detect_plan_mode_from_context(prompt, workflow_state)

        assert workflow_state.variables.get("plan_mode") is True

    def test_ignores_prompt_without_indicators(self, workflow_state) -> None:
        """Ignores prompts without plan mode indicators."""
        prompt = "Please fix the bug in the code."

        detect_plan_mode_from_context(prompt, workflow_state)

        assert "plan_mode" not in workflow_state.variables

    def test_handles_empty_prompt(self, workflow_state) -> None:
        """Handles empty prompt gracefully."""
        detect_plan_mode_from_context("", workflow_state)

        assert "plan_mode" not in workflow_state.variables

    def test_handles_none_prompt(self, workflow_state) -> None:
        """Handles None prompt gracefully."""
        detect_plan_mode_from_context(None, workflow_state)  # type: ignore[arg-type]

        assert "plan_mode" not in workflow_state.variables


# =============================================================================
# Tests for handle_detect_plan_mode_from_context (action handler)
# =============================================================================


class TestHandleDetectPlanModeFromContext:
    """Tests for the async action handler wrapper."""

    @pytest.mark.asyncio
    async def test_detects_plan_mode_from_event_data(self, workflow_state) -> None:
        """Action handler reads prompt from event_data and detects plan mode."""
        context = MagicMock()
        context.state = workflow_state
        context.event_data = {
            "prompt": "<system-reminder>Plan mode is active</system-reminder>"
        }

        result = await handle_detect_plan_mode_from_context(context)

        assert result is None
        assert workflow_state.variables.get("plan_mode") is True

    @pytest.mark.asyncio
    async def test_handles_missing_event_data(self, workflow_state) -> None:
        """Action handler handles None event_data gracefully."""
        context = MagicMock()
        context.state = workflow_state
        context.event_data = None

        result = await handle_detect_plan_mode_from_context(context)

        assert result is None
        assert "plan_mode" not in workflow_state.variables

    @pytest.mark.asyncio
    async def test_handles_empty_prompt_in_event_data(self, workflow_state) -> None:
        """Action handler handles empty prompt in event_data."""
        context = MagicMock()
        context.state = workflow_state
        context.event_data = {"prompt": ""}

        result = await handle_detect_plan_mode_from_context(context)

        assert result is None
        assert "plan_mode" not in workflow_state.variables

    @pytest.mark.asyncio
    async def test_detects_exit_plan_mode(self, workflow_state) -> None:
        """Action handler detects plan mode exit from system reminders."""
        workflow_state.variables["plan_mode"] = True
        context = MagicMock()
        context.state = workflow_state
        context.event_data = {
            "prompt": "<system-reminder>Exited Plan Mode</system-reminder>"
        }

        result = await handle_detect_plan_mode_from_context(context)

        assert result is None
        assert workflow_state.variables.get("plan_mode") is False


# =============================================================================
# Tests for detect_task_claim - close_task behavior
# =============================================================================


class TestDetectTaskClaimCloseTaskBehavior:
    """Tests for detect_task_claim close_task behavior.

    close_task is handled in two places for broad CLI support:
    1. MCP proxy (_lifecycle.py) - for Claude Code which doesn't include tool_result
    2. detect_task_claim - for CLIs that do send tool_result (Gemini, Codex)

    These tests verify that detect_task_claim correctly handles close_task:
    - Successful close_task clears task_claimed
    - Failed close_task leaves task_claimed unchanged
    """

    def test_successful_close_task_clears_task_claimed(
        self, workflow_state, make_after_tool_event
    ) -> None:
        """Successful close_task should clear task_claimed for CLIs that send tool_result."""
        workflow_state.variables["task_claimed"] = True
        workflow_state.variables["claimed_task_id"] = "task-123"

        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "close_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={"success": True, "result": {"id": "task-123", "status": "done"}},
        )

        detect_task_claim(event, workflow_state)

        # Task claim should be cleared on successful close
        assert workflow_state.variables.get("task_claimed") is False
        assert workflow_state.variables.get("claimed_task_id") is None

    def test_failed_close_task_with_error(self, workflow_state, make_after_tool_event) -> None:
        """close_task with error should NOT clear task_claimed."""
        workflow_state.variables["task_claimed"] = True
        workflow_state.variables["claimed_task_id"] = "task-123"

        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "close_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={
                "success": True,
                "result": {
                    "error": "uncommitted_changes",
                    "message": "Task has uncommitted changes",
                },
            },
        )

        detect_task_claim(event, workflow_state)

        # Task claim should remain unchanged
        assert workflow_state.variables.get("task_claimed") is True
        assert workflow_state.variables.get("claimed_task_id") == "task-123"

    def test_close_task_with_empty_output(self, workflow_state, make_after_tool_event) -> None:
        """close_task with no tool output should NOT clear task_claimed (might be Claude Code)."""
        workflow_state.variables["task_claimed"] = True
        workflow_state.variables["claimed_task_id"] = "task-123"

        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "close_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={},  # No output
        )

        detect_task_claim(event, workflow_state)

        # Should remain unchanged (MCP proxy handles Claude Code clear)
        assert workflow_state.variables.get("task_claimed") is True

    def test_close_task_with_top_level_error(self, workflow_state, make_after_tool_event) -> None:
        """close_task with top-level error should NOT clear task_claimed."""
        workflow_state.variables["task_claimed"] = True
        workflow_state.variables["claimed_task_id"] = "task-123"

        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "close_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={"status": "error", "error": "Something went wrong"},
        )

        detect_task_claim(event, workflow_state)

        assert workflow_state.variables.get("task_claimed") is True


# =============================================================================
# Tests for detect_task_claim - claim operations
# =============================================================================


class TestDetectTaskClaimClaimOperations:
    """Tests for detect_task_claim function, claim operations."""

    def test_sets_task_claimed_on_claim_task(
        self, workflow_state, make_after_tool_event, mock_task_manager
    ) -> None:
        """claim_task sets task_claimed=True and stores task ID."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "claim_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={"success": True, "result": {"id": "task-123", "status": "in_progress"}},
        )

        detect_task_claim(event, workflow_state, task_manager=mock_task_manager)

        assert workflow_state.variables.get("task_claimed") is True
        # Should store the UUID from the mock task, not the raw ID if it was looked up
        # If raw ID passed in arguments is 'task-123', mock returns 'task-uuid-123'.
        assert workflow_state.variables.get("claimed_task_id") == "task-uuid-123"

    def test_sets_task_claimed_on_create_task(
        self, workflow_state, make_after_tool_event, mock_task_manager
    ) -> None:
        """create_task sets task_claimed=True and stores new task ID."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "create_task",
                "arguments": {"title": "New task"},
            },
            # create_task returns UUID in result, doesn't need task_manager lookup usually
            # unless we changed that logic.
            # Logic: inner_tool_name == "create_task": task_id = result.get("id")
            tool_output={"success": True, "result": {"id": "new-task-uuid", "status": "open"}},
        )

        detect_task_claim(event, workflow_state, task_manager=mock_task_manager)

        assert workflow_state.variables.get("task_claimed") is True
        assert workflow_state.variables.get("claimed_task_id") == "new-task-uuid"

    def test_create_task_handles_missing_id(
        self, workflow_state, make_after_tool_event, mock_task_manager
    ) -> None:
        """create_task with missing ID in response (e.g. error) should not set claimed."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "create_task",
                "arguments": {"title": "New task"},
            },
            tool_output={"success": True, "result": {"status": "error"}},  # No ID
        )

        detect_task_claim(event, workflow_state, task_manager=mock_task_manager)

        assert "task_claimed" not in workflow_state.variables

    def test_sets_task_claimed_on_update_to_in_progress(
        self, workflow_state, make_after_tool_event, mock_task_manager
    ) -> None:
        """update_task with status=in_progress sets task_claimed=True."""
        # Setup mock to return specific ID for this test
        mock_task = mock_task_manager.get_task.return_value
        mock_task.id = "task-uuid-456"

        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "update_task",
                "arguments": {"task_id": "task-123", "status": "in_progress"},
            },
            tool_output={"success": True, "result": {"id": "task-123", "status": "in_progress"}},
        )

        detect_task_claim(event, workflow_state, task_manager=mock_task_manager)

        assert workflow_state.variables.get("task_claimed") is True
        assert workflow_state.variables.get("claimed_task_id") == "task-uuid-456"

    def test_ignores_update_to_other_status(self, workflow_state, make_after_tool_event) -> None:
        """update_task with status other than in_progress is ignored."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "update_task",
                "arguments": {"task_id": "task-123", "status": "blocked"},
            },
            tool_output={"success": True, "result": {"id": "task-123", "status": "blocked"}},
        )

        detect_task_claim(event, workflow_state)

        assert "task_claimed" not in workflow_state.variables

    def test_does_not_set_task_claimed_on_claim_error(
        self, workflow_state, make_after_tool_event
    ) -> None:
        """claim_task with error response does NOT set task_claimed."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "claim_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={
                "success": True,
                "result": {"error": "already_claimed", "message": "Task is already claimed"},
            },
        )

        detect_task_claim(event, workflow_state)

        assert "task_claimed" not in workflow_state.variables

    def test_ignores_non_gobby_tasks_server(self, workflow_state, make_after_tool_event) -> None:
        """Calls to other MCP servers are ignored."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "other-server",
                "tool_name": "claim_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={"success": True, "result": {}},
        )

        detect_task_claim(event, workflow_state)

        assert "task_claimed" not in workflow_state.variables

    def test_ignores_non_mcp_tools(self, workflow_state, make_after_tool_event) -> None:
        """Non-MCP tool calls are ignored."""
        event = make_after_tool_event(
            "Read",
            tool_input={"file_path": "/some/file.py"},
            tool_output={"content": "file content"},
        )

        detect_task_claim(event, workflow_state)

        assert "task_claimed" not in workflow_state.variables

    def test_task_resolution_without_manager_warns(
        self, workflow_state, make_after_tool_event
    ) -> None:
        """When task_manager is None, logs warning but doesn't crash."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "claim_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={"success": True, "result": {"id": "task-123", "status": "in_progress"}},
        )

        detect_task_claim(event, workflow_state, task_manager=None)

        # Should NOT claim task because UUID couldn't be resolved
        assert "task_claimed" not in workflow_state.variables
        assert "claimed_task_id" not in workflow_state.variables

    def test_task_resolution_failure_is_handled(
        self, workflow_state, make_after_tool_event, mock_task_manager
    ) -> None:
        """Exceptions during task resolution are handled gracefully."""
        # Mock lookup to raise exception
        mock_task_manager.get_task.side_effect = Exception("DB Error")

        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "claim_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={"success": True, "result": {"id": "task-123", "status": "in_progress"}},
        )

        detect_task_claim(event, workflow_state, task_manager=mock_task_manager)

        # Should not claim task
        assert "task_claimed" not in workflow_state.variables

    def test_task_not_found(self, workflow_state, make_after_tool_event, mock_task_manager) -> None:
        """If task is not found by manager, does not claim."""
        mock_task_manager.get_task.return_value = None

        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "claim_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={"success": True, "result": {"id": "task-123", "status": "in_progress"}},
        )

        detect_task_claim(event, workflow_state, task_manager=mock_task_manager)

        assert "task_claimed" not in workflow_state.variables

    def test_auto_link_failure_handled(
        self, workflow_state, make_after_tool_event, mock_task_manager
    ) -> None:
        """If linking session fails, still claims task (errors logged not raised)."""
        mock_session_manager = MagicMock()
        mock_session_manager.link_task.side_effect = Exception("Link error")

        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "claim_task",
                "arguments": {"task_id": "task-123"},
            },
            tool_output={"success": True, "result": {"id": "task-123", "status": "in_progress"}},
        )

        detect_task_claim(
            event,
            workflow_state,
            task_manager=mock_task_manager,
            session_task_manager=mock_session_manager,
        )

        # Task claim should still succeed even if linking failed
        assert workflow_state.variables.get("task_claimed") is True


# =============================================================================
# Tests for detect_mcp_call
# =============================================================================


class TestDetectMcpCall:
    """Tests for detect_mcp_call function."""

    def test_tracks_successful_mcp_call(self, workflow_state, make_after_tool_event) -> None:
        """Tracks successful MCP call in state variables."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={"server_name": "demo-server", "tool_name": "demo-tool"},
            tool_output={"result": "success"},
        )

        detect_mcp_call(event, workflow_state)

        # Check mcp_calls tracking
        mcp_calls = workflow_state.variables.get("mcp_calls", {})
        assert "demo-server" in mcp_calls
        assert "demo-tool" in mcp_calls["demo-server"]

        # Check mcp_results tracking
        mcp_results = workflow_state.variables.get("mcp_results", {})
        assert "demo-server" in mcp_results
        assert mcp_results["demo-server"]["demo-tool"] == "success"

    def test_tracks_multiple_tools(self, workflow_state, make_after_tool_event) -> None:
        """Tracks multiple unique tools for same server."""
        event1 = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={"server_name": "demo-server", "tool_name": "tool-1"},
            tool_output={"result": "1"},
        )
        event2 = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={"server_name": "demo-server", "tool_name": "tool-2"},
            tool_output={"result": "2"},
        )

        detect_mcp_call(event1, workflow_state)
        detect_mcp_call(event2, workflow_state)

        calls = workflow_state.variables["mcp_calls"]["demo-server"]
        assert "tool-1" in calls
        assert "tool-2" in calls

    def test_ignores_error_responses(self, workflow_state, make_after_tool_event) -> None:
        """Does NOT track MCP calls that returned an error."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={"server_name": "demo-server", "tool_name": "error-tool"},
            tool_output={"error": "failed"},
        )

        detect_mcp_call(event, workflow_state)

        assert "mcp_calls" not in workflow_state.variables

    def test_ignores_nested_error_result(self, workflow_state, make_after_tool_event) -> None:
        """Does NOT track MCP calls where result itself indicates error."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={"server_name": "demo-server", "tool_name": "error-tool"},
            tool_output={"result": {"error": "nested failure"}},
        )

        detect_mcp_call(event, workflow_state)

        assert "mcp_calls" not in workflow_state.variables

    def test_ignores_missing_server_or_tool(self, workflow_state, make_after_tool_event) -> None:
        """Ignores calls missing server or tool name."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={"server_name": "", "tool_name": "tool"},  # Missing server
            tool_output={"result": "ok"},
        )

        detect_mcp_call(event, workflow_state)
        assert "mcp_calls" not in workflow_state.variables


# =============================================================================
# Tests for process_mcp_handlers template rendering
# =============================================================================


class TestProcessMcpHandlersTemplateRendering:
    """Tests for template rendering in on_mcp_success/on_mcp_error handlers."""

    def test_renders_template_value_with_result_context(self, workflow_state) -> None:
        """Template values like '{{ result.task_id }}' are rendered using MCP result."""
        from gobby.workflows.templates import TemplateEngine

        # Simulate tracked MCP result (set by detect_mcp_call before handlers run)
        workflow_state.variables["mcp_results"] = {
            "gobby-tasks": {"suggest_next_task": {"task_id": "abc-123", "title": "Test"}}
        }

        on_success = [
            {
                "server": "gobby-tasks",
                "tool": "suggest_next_task",
                "action": "set_variable",
                "variable": "current_task_id",
                "value": "{{ result.task_id }}",
            }
        ]

        process_mcp_handlers(
            workflow_state,
            server_name="gobby-tasks",
            tool_name="suggest_next_task",
            succeeded=True,
            on_mcp_success=on_success,
            on_mcp_error=[],
            template_engine=TemplateEngine(),
        )

        assert workflow_state.variables["current_task_id"] == "abc-123"

    def test_stores_literal_value_without_template(self, workflow_state) -> None:
        """Non-template values are stored as-is."""
        on_success = [
            {
                "server": "gobby-tasks",
                "tool": "claim_task",
                "action": "set_variable",
                "variable": "task_claimed",
                "value": True,
            }
        ]

        process_mcp_handlers(
            workflow_state,
            server_name="gobby-tasks",
            tool_name="claim_task",
            succeeded=True,
            on_mcp_success=on_success,
            on_mcp_error=[],
        )

        assert workflow_state.variables["task_claimed"] is True

    def test_renders_template_without_engine_stores_literal(self, workflow_state) -> None:
        """Without template_engine, template strings are stored as-is."""
        workflow_state.variables["mcp_results"] = {
            "gobby-tasks": {"suggest_next_task": {"task_id": "abc-123"}}
        }

        on_success = [
            {
                "server": "gobby-tasks",
                "tool": "suggest_next_task",
                "action": "set_variable",
                "variable": "current_task_id",
                "value": "{{ result.task_id }}",
            }
        ]

        process_mcp_handlers(
            workflow_state,
            server_name="gobby-tasks",
            tool_name="suggest_next_task",
            succeeded=True,
            on_mcp_success=on_success,
            on_mcp_error=[],
            template_engine=None,  # No engine
        )

        # Without engine, the template string is stored literally
        assert workflow_state.variables["current_task_id"] == "{{ result.task_id }}"

    def test_error_handler_with_template(self, workflow_state) -> None:
        """on_mcp_error handlers also support template rendering."""
        from gobby.workflows.templates import TemplateEngine

        workflow_state.variables["mcp_results"] = {}

        on_error = [
            {
                "server": "gobby-tasks",
                "tool": "claim_task",
                "action": "set_variable",
                "variable": "error_msg",
                "value": "failed",
            }
        ]

        process_mcp_handlers(
            workflow_state,
            server_name="gobby-tasks",
            tool_name="claim_task",
            succeeded=False,
            on_mcp_success=[],
            on_mcp_error=on_error,
            template_engine=TemplateEngine(),
        )

        assert workflow_state.variables["error_msg"] == "failed"
