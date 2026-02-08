"""Tests for skill hints in hook error messages.

Verifies that hook error messages include actionable instructions
when blocking actions (e.g., create/claim task instructions when edit blocked).
"""

import pytest

from gobby.workflows.enforcement import require_active_task

pytestmark = pytest.mark.unit


class TestRequireActiveTaskSkillHint:
    """Tests for instructions in require_active_task error messages."""

    @pytest.mark.asyncio
    async def test_block_message_includes_task_instructions(self) -> None:
        """Verify blocked edit includes task creation instructions in reason."""
        # Create minimal event_data for a protected tool
        event_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/some/file.py"},
        }

        # Mock config with require_task_before_edit=True
        class MockConfig:
            class MockWorkflow:
                require_task_before_edit = True
                protected_tools = ["Edit", "Write", "NotebookEdit"]

            workflow = MockWorkflow()

        # Call with no task manager (will still block)
        result = await require_active_task(
            task_manager=None,
            session_id="test-session",
            config=MockConfig(),  # type: ignore
            event_data=event_data,
            project_id="test-project",
            workflow_state=None,
        )

        assert result is not None, "Should block when no task claimed"
        assert result["decision"] == "block"
        # Should include task creation instructions
        reason = result["reason"].lower()
        assert "task" in reason, (
            f"Block reason should mention tasks.\nGot: {result['reason']}"
        )

    @pytest.mark.asyncio
    async def test_inject_context_includes_task_instructions(self) -> None:
        """Verify blocked edit includes task instructions in inject_context."""
        event_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/some/file.py"},
        }

        class MockConfig:
            class MockWorkflow:
                require_task_before_edit = True
                protected_tools = ["Edit", "Write", "NotebookEdit"]

            workflow = MockWorkflow()

        result = await require_active_task(
            task_manager=None,
            session_id="test-session",
            config=MockConfig(),  # type: ignore
            event_data=event_data,
            project_id="test-project",
            workflow_state=None,
        )

        assert result is not None
        # inject_context should include task instructions
        inject_context = result.get("inject_context", "")
        assert "task" in inject_context.lower(), (
            f"inject_context should mention tasks.\nGot: {inject_context}"
        )

    @pytest.mark.asyncio
    async def test_skill_hint_includes_usage_instruction(self) -> None:
        """Verify skill hint includes how to create/claim a task."""
        event_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/some/file.py"},
        }

        class MockConfig:
            class MockWorkflow:
                require_task_before_edit = True
                protected_tools = ["Edit", "Write", "NotebookEdit"]

            workflow = MockWorkflow()

        result = await require_active_task(
            task_manager=None,
            session_id="test-session",
            config=MockConfig(),  # type: ignore
            event_data=event_data,
            project_id="test-project",
            workflow_state=None,
        )

        assert result is not None
        # Should include instruction on how to create/claim a task
        reason = result["reason"].lower()
        inject_context = result.get("inject_context", "").lower()
        combined = reason + inject_context

        # Should mention how to create or claim a task
        assert "create" in combined or "claim" in combined, (
            f"Should include task creation instruction.\nGot: {result['reason']}"
        )


class TestShortReminderSkillHint:
    """Tests for short reminder (after error already shown)."""

    @pytest.mark.asyncio
    async def test_short_reminder_still_mentions_task(self) -> None:
        """Verify short reminder (2nd+ block) still references tasks."""

        class MockWorkflowState:
            variables: dict = {}

            def __init__(self) -> None:
                self.variables = {"task_error_shown": True}  # Already shown error once

        event_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/some/file.py"},
        }

        class MockConfig:
            class MockWorkflow:
                require_task_before_edit = True
                protected_tools = ["Edit", "Write", "NotebookEdit"]

            workflow = MockWorkflow()

        result = await require_active_task(
            task_manager=None,
            session_id="test-session",
            config=MockConfig(),  # type: ignore
            event_data=event_data,
            project_id="test-project",
            workflow_state=MockWorkflowState(),  # type: ignore
        )

        assert result is not None
        assert result["decision"] == "block"
        # Short reminder should still be helpful
        reason = result.get("reason", "")
        inject_context = result.get("inject_context", "")
        combined = (reason + inject_context).lower()

        # Should mention task or reference to previous instructions
        has_task_ref = "task" in combined
        has_prev_ref = "previous" in combined

        assert has_task_ref or has_prev_ref, (
            f"Short reminder should mention task or reference previous instructions.\n"
            f"Got reason: {reason}\nGot inject_context: {inject_context}"
        )
