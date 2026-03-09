"""Tests for CodexChatSessionPermissionsMixin.

Covers:
- Plan mode blocking of write tools
- Plan mode allowing read tools
- Plan file exceptions
- Bash write pattern detection
- Dangerous bash detection
- Tool approval flow
- Approval handler routing
- Mode transitions
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from gobby.servers.codex_chat_session_permissions import CodexChatSessionPermissionsMixin

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Concrete test implementation of the mixin
# ---------------------------------------------------------------------------


class FakeCodexSession(CodexChatSessionPermissionsMixin):
    """Minimal implementation for testing the permissions mixin."""

    def __init__(self, chat_mode: str = "plan") -> None:
        self.conversation_id = "test-conv"
        self.chat_mode = chat_mode
        self._on_mode_changed = None
        self._on_pre_tool = None
        self._pending_question = None
        self._pending_answers = None
        self._pending_answer_event = None
        self._approved_tools: set[str] = set()
        self._tool_approval_config = None
        self._tool_approval_callback = None
        self._plan_approved = False
        self._plan_feedback = None
        self._plan_file_path = None
        self._on_mode_persist = None
        self._pending_approval = None
        self._pending_approval_decision = None
        self._pending_approval_event = None


# ---------------------------------------------------------------------------
# Plan mode blocking
# ---------------------------------------------------------------------------


class TestPlanModeBlocking:
    @pytest.mark.asyncio
    async def test_edit_blocked_in_plan_mode(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission("Edit", {"file_path": "/tmp/foo.py"})
        assert result["decision"] == "decline"
        assert "Plan mode" in result["reason"]

    @pytest.mark.asyncio
    async def test_write_blocked_in_plan_mode(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission("Write", {"file_path": "/tmp/bar.py"})
        assert result["decision"] == "decline"

    @pytest.mark.asyncio
    async def test_notebook_edit_blocked_in_plan_mode(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission("NotebookEdit", {})
        assert result["decision"] == "decline"

    @pytest.mark.asyncio
    async def test_read_allowed_in_plan_mode(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission("Read", {"file_path": "/tmp/foo.py"})
        assert result["decision"] == "accept"

    @pytest.mark.asyncio
    async def test_glob_allowed_in_plan_mode(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission("Glob", {"pattern": "*.py"})
        assert result["decision"] == "accept"

    @pytest.mark.asyncio
    async def test_bash_read_allowed_in_plan_mode(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission("Bash", {"command": "ls -la"})
        assert result["decision"] == "accept"

    @pytest.mark.asyncio
    async def test_bash_write_blocked_in_plan_mode(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission("Bash", {"command": "rm -rf /tmp/test"})
        assert result["decision"] == "decline"

    @pytest.mark.asyncio
    async def test_bash_git_commit_blocked_in_plan_mode(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission("Bash", {"command": "git commit -m 'test'"})
        assert result["decision"] == "decline"


# ---------------------------------------------------------------------------
# Plan file exceptions
# ---------------------------------------------------------------------------


class TestPlanFileExceptions:
    @pytest.mark.asyncio
    async def test_write_to_plan_file_allowed(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission(
            "Write", {"file_path": ".gobby/plans/my-plan.md"}
        )
        assert result["decision"] == "accept"
        assert session._plan_file_path == ".gobby/plans/my-plan.md"

    @pytest.mark.asyncio
    async def test_edit_to_claude_plan_file_allowed(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        result = await session._check_tool_permission(
            "Edit", {"file_path": ".claude/plans/plan.md"}
        )
        assert result["decision"] == "accept"


# ---------------------------------------------------------------------------
# Approval handler routing
# ---------------------------------------------------------------------------


class TestApprovalHandlerRouting:
    @pytest.mark.asyncio
    async def test_pre_tool_callback_can_block(self) -> None:
        """on_pre_tool returning block decision causes decline."""
        session = FakeCodexSession(chat_mode="accept_edits")
        session._on_pre_tool = AsyncMock(
            return_value={"decision": "block", "reason": "Rule blocked it"}
        )

        result = await session._check_tool_permission("Edit", {"file_path": "test.py"})
        assert result["decision"] == "decline"
        assert "Rule blocked it" in result["reason"]

    @pytest.mark.asyncio
    async def test_pre_tool_callback_allows(self) -> None:
        """on_pre_tool returning allow lets the tool through."""
        session = FakeCodexSession(chat_mode="accept_edits")
        session._on_pre_tool = AsyncMock(return_value={"decision": "allow"})

        result = await session._check_tool_permission("Edit", {"file_path": "test.py"})
        assert result["decision"] == "accept"

    @pytest.mark.asyncio
    async def test_no_callback_allows(self) -> None:
        """Without on_pre_tool callback, tools are accepted."""
        session = FakeCodexSession(chat_mode="accept_edits")
        result = await session._check_tool_permission("Edit", {"file_path": "test.py"})
        assert result["decision"] == "accept"


# ---------------------------------------------------------------------------
# Mode transitions
# ---------------------------------------------------------------------------


class TestModeTransitions:
    def test_set_chat_mode_plan_resets_state(self) -> None:
        session = FakeCodexSession(chat_mode="accept_edits")
        session._plan_approved = True
        session._plan_feedback = "old feedback"
        session.set_chat_mode("plan")
        assert session.chat_mode == "plan"
        assert session._plan_approved is False
        assert session._plan_feedback is None

    def test_provide_plan_decision_approve(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        session.provide_plan_decision("approve")
        assert session._plan_approved is True
        assert session.chat_mode == "accept_edits"

    def test_has_pending_plan_always_false(self) -> None:
        """Codex doesn't have ExitPlanMode, so no pending plan."""
        session = FakeCodexSession(chat_mode="plan")
        assert session.has_pending_plan is False

    @pytest.mark.asyncio
    async def test_approved_plan_unblocks_write(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        session._plan_approved = True
        result = await session._check_tool_permission("Edit", {"file_path": "test.py"})
        assert result["decision"] == "accept"


# ---------------------------------------------------------------------------
# Plan mode context
# ---------------------------------------------------------------------------


class TestPlanModeContext:
    def test_active_plan_context(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        ctx = session._consume_plan_mode_context()
        assert ctx is not None
        assert "PLAN MODE" in ctx
        assert "BLOCKED" in ctx

    def test_approved_plan_context(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        session._plan_approved = True
        ctx = session._consume_plan_mode_context()
        assert ctx is not None
        assert "approved" in ctx

    def test_no_context_outside_plan_mode(self) -> None:
        session = FakeCodexSession(chat_mode="accept_edits")
        ctx = session._consume_plan_mode_context()
        assert ctx is None

    def test_feedback_consumed(self) -> None:
        session = FakeCodexSession(chat_mode="plan")
        session._plan_feedback = "Please add error handling"
        ctx = session._consume_plan_mode_context()
        assert "Please add error handling" in ctx
        # Feedback should be consumed (cleared)
        assert session._plan_feedback is None


# ---------------------------------------------------------------------------
# Tool approval flow
# ---------------------------------------------------------------------------


class TestToolApprovalFlow:
    @pytest.mark.asyncio
    async def test_approval_accept(self) -> None:
        session = FakeCodexSession(chat_mode="accept_edits")

        # Simulate approval in background
        async def _approve_after_delay() -> None:
            await asyncio.sleep(0.01)
            session.provide_approval("approve")

        task = asyncio.create_task(_approve_after_delay())

        result = await session._wait_for_tool_approval("mcp__test__call", {})
        assert result["decision"] == "accept"
        await task

    @pytest.mark.asyncio
    async def test_approval_reject(self) -> None:
        session = FakeCodexSession(chat_mode="accept_edits")

        async def _reject_after_delay() -> None:
            await asyncio.sleep(0.01)
            session.provide_approval("reject")

        task = asyncio.create_task(_reject_after_delay())

        result = await session._wait_for_tool_approval("mcp__test__call", {})
        assert result["decision"] == "decline"
        assert "rejected" in result["reason"]
        await task

    @pytest.mark.asyncio
    async def test_approval_approve_always(self) -> None:
        session = FakeCodexSession(chat_mode="accept_edits")

        async def _always_after_delay() -> None:
            await asyncio.sleep(0.01)
            session.provide_approval("approve_always")

        task = asyncio.create_task(_always_after_delay())

        result = await session._wait_for_tool_approval("mcp__test__call", {})
        assert result["decision"] == "accept"
        assert "mcp__test__call" in session._approved_tools
        await task

    def test_has_pending_approval(self) -> None:
        session = FakeCodexSession()
        assert session.has_pending_approval is False
        session._pending_approval = {"tool_name": "test", "arguments": {}}
        assert session.has_pending_approval is True


# ---------------------------------------------------------------------------
# Dangerous bash detection
# ---------------------------------------------------------------------------


class TestDangerousBash:
    @pytest.mark.asyncio
    async def test_dangerous_bash_needs_approval_in_accept_edits(self) -> None:
        session = FakeCodexSession(chat_mode="accept_edits")

        # Set up auto-approval to avoid blocking
        async def _auto_approve() -> None:
            await asyncio.sleep(0.01)
            session.provide_approval("approve")

        task = asyncio.create_task(_auto_approve())
        result = await session._check_tool_permission("Bash", {"command": "sudo rm -rf /"})
        # Should have gone through approval flow (accepted)
        assert result["decision"] == "accept"
        await task

    def test_safe_bash_not_dangerous(self) -> None:
        session = FakeCodexSession()
        assert not session._is_dangerous_bash({"command": "ls -la"})
        assert not session._is_dangerous_bash({"command": "cat file.txt"})

    def test_dangerous_patterns_detected(self) -> None:
        session = FakeCodexSession()
        assert session._is_dangerous_bash({"command": "sudo apt install foo"})
        assert session._is_dangerous_bash({"command": "rm -rf /tmp"})
        assert session._is_dangerous_bash({"command": "git push --force"})
