"""Tests for workflow detection helper functions."""

from datetime import UTC, datetime

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.detection_helpers import (
    detect_plan_mode,
    detect_plan_mode_from_context,
    detect_task_claim,
)


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
# Tests for detect_plan_mode (tool-based detection)
# =============================================================================


class TestDetectPlanMode:
    """Tests for detect_plan_mode function."""

    def test_enters_plan_mode_on_enter_tool(self, workflow_state, make_after_tool_event):
        """EnterPlanMode tool sets plan_mode=True."""
        event = make_after_tool_event("EnterPlanMode")

        detect_plan_mode(event, workflow_state)

        assert workflow_state.variables.get("plan_mode") is True

    def test_exits_plan_mode_on_exit_tool(self, workflow_state, make_after_tool_event):
        """ExitPlanMode tool sets plan_mode=False."""
        workflow_state.variables["plan_mode"] = True
        event = make_after_tool_event("ExitPlanMode")

        detect_plan_mode(event, workflow_state)

        assert workflow_state.variables.get("plan_mode") is False

    def test_ignores_other_tools(self, workflow_state, make_after_tool_event):
        """Other tools do not affect plan_mode."""
        event = make_after_tool_event("Read")

        detect_plan_mode(event, workflow_state)

        assert "plan_mode" not in workflow_state.variables

    def test_handles_empty_event_data(self, workflow_state):
        """Handles event with no data gracefully."""
        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            source=SessionSource.CLAUDE,
            session_id="test-session-ext",
            timestamp=datetime.now(UTC),
            data=None,
            metadata={},
        )

        detect_plan_mode(event, workflow_state)

        assert "plan_mode" not in workflow_state.variables


# =============================================================================
# Tests for detect_plan_mode_from_context (system reminder detection)
# =============================================================================


class TestDetectPlanModeFromContext:
    """Tests for detect_plan_mode_from_context function."""

    def test_detects_plan_mode_active_indicator(self, workflow_state, make_before_agent_event):
        """Detects 'Plan mode is active' in prompt."""
        event = make_before_agent_event(
            "User prompt here\n<system-reminder>Plan mode is active</system-reminder>"
        )

        detect_plan_mode_from_context(event, workflow_state)

        assert workflow_state.variables.get("plan_mode") is True

    def test_detects_plan_mode_still_active(self, workflow_state, make_before_agent_event):
        """Detects 'Plan mode still active' in prompt."""
        event = make_before_agent_event(
            "<system-reminder>Plan mode still active</system-reminder>\nWhat should I do?"
        )

        detect_plan_mode_from_context(event, workflow_state)

        assert workflow_state.variables.get("plan_mode") is True

    def test_detects_you_are_in_plan_mode(self, workflow_state, make_before_agent_event):
        """Detects 'You are in plan mode' in prompt."""
        event = make_before_agent_event(
            "<system-reminder>You are in plan mode</system-reminder>. Please continue planning."
        )

        detect_plan_mode_from_context(event, workflow_state)

        assert workflow_state.variables.get("plan_mode") is True

    def test_detects_exited_plan_mode(self, workflow_state, make_before_agent_event):
        """Detects 'Exited Plan Mode' in prompt."""
        workflow_state.variables["plan_mode"] = True
        event = make_before_agent_event(
            "<system-reminder>Exited Plan Mode</system-reminder>. Now implement the changes."
        )

        detect_plan_mode_from_context(event, workflow_state)

        assert workflow_state.variables.get("plan_mode") is False

    def test_does_not_change_when_already_in_plan_mode(
        self, workflow_state, make_before_agent_event
    ):
        """Does not log again if already in plan mode."""
        workflow_state.variables["plan_mode"] = True
        event = make_before_agent_event("Plan mode is active")

        # Should not raise or change state
        detect_plan_mode_from_context(event, workflow_state)

        assert workflow_state.variables.get("plan_mode") is True

    def test_ignores_prompt_without_indicators(self, workflow_state, make_before_agent_event):
        """Ignores prompts without plan mode indicators."""
        event = make_before_agent_event("Please fix the bug in the code.")

        detect_plan_mode_from_context(event, workflow_state)

        assert "plan_mode" not in workflow_state.variables

    def test_handles_empty_event_data(self, workflow_state):
        """Handles event with no data gracefully."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            source=SessionSource.CLAUDE,
            session_id="test-session-ext",
            timestamp=datetime.now(UTC),
            data=None,
            metadata={},
        )

        detect_plan_mode_from_context(event, workflow_state)

        assert "plan_mode" not in workflow_state.variables

    def test_handles_empty_prompt(self, workflow_state, make_before_agent_event):
        """Handles empty prompt gracefully."""
        event = make_before_agent_event("")

        detect_plan_mode_from_context(event, workflow_state)

        assert "plan_mode" not in workflow_state.variables


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

    def test_successful_close_task_clears_task_claimed(self, workflow_state, make_after_tool_event):
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

    def test_failed_close_task_with_error(self, workflow_state, make_after_tool_event):
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


# =============================================================================
# Tests for detect_task_claim - claim operations
# =============================================================================


class TestDetectTaskClaimClaimOperations:
    """Tests for detect_task_claim function, claim operations."""

    def test_sets_task_claimed_on_claim_task(self, workflow_state, make_after_tool_event):
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

        detect_task_claim(event, workflow_state)

        assert workflow_state.variables.get("task_claimed") is True
        assert workflow_state.variables.get("claimed_task_id") == "task-123"

    def test_sets_task_claimed_on_create_task(self, workflow_state, make_after_tool_event):
        """create_task sets task_claimed=True and stores new task ID."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "create_task",
                "arguments": {"title": "New task"},
            },
            tool_output={"success": True, "result": {"id": "new-task-id", "status": "open"}},
        )

        detect_task_claim(event, workflow_state)

        assert workflow_state.variables.get("task_claimed") is True
        assert workflow_state.variables.get("claimed_task_id") == "new-task-id"

    def test_sets_task_claimed_on_update_to_in_progress(
        self, workflow_state, make_after_tool_event
    ):
        """update_task with status=in_progress sets task_claimed=True."""
        event = make_after_tool_event(
            "mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "update_task",
                "arguments": {"task_id": "task-123", "status": "in_progress"},
            },
            tool_output={"success": True, "result": {"id": "task-123", "status": "in_progress"}},
        )

        detect_task_claim(event, workflow_state)

        assert workflow_state.variables.get("task_claimed") is True
        assert workflow_state.variables.get("claimed_task_id") == "task-123"

    def test_ignores_update_to_other_status(self, workflow_state, make_after_tool_event):
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

    def test_does_not_set_task_claimed_on_claim_error(self, workflow_state, make_after_tool_event):
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

    def test_ignores_non_gobby_tasks_server(self, workflow_state, make_after_tool_event):
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

    def test_ignores_non_mcp_tools(self, workflow_state, make_after_tool_event):
        """Non-MCP tool calls are ignored."""
        event = make_after_tool_event(
            "Read",
            tool_input={"file_path": "/some/file.py"},
            tool_output={"content": "file content"},
        )

        detect_task_claim(event, workflow_state)

        assert "task_claimed" not in workflow_state.variables
