"""Tests for ExitPlanMode permission handling in ChatSessionPermissionsMixin.

Verifies the fail-closed behavior: if no explicit decision is provided,
ExitPlanMode should deny (request_changes), not approve.
"""

import asyncio

import pytest

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

from gobby.servers.chat_session import ChatSession

pytestmark = pytest.mark.unit


@pytest.fixture
def session() -> ChatSession:
    s = ChatSession(conversation_id="test-plan-perm")
    s.set_chat_mode("plan")
    return s


class TestExitPlanModeDecision:
    """ExitPlanMode should block until a decision and fail closed on missing decisions."""

    @pytest.mark.asyncio
    async def test_approve_returns_allow(self, session: ChatSession) -> None:
        """Explicit 'approve' decision should return PermissionResultAllow."""

        async def approve_after_delay() -> None:
            await asyncio.sleep(0.05)
            session.provide_plan_decision("approve")

        task = asyncio.create_task(approve_after_delay())
        result = await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
        await task

        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.asyncio
    async def test_request_changes_returns_deny(self, session: ChatSession) -> None:
        """Explicit 'request_changes' decision should return PermissionResultDeny."""

        async def reject_after_delay() -> None:
            await asyncio.sleep(0.05)
            session.provide_plan_decision("request_changes")

        task = asyncio.create_task(reject_after_delay())
        result = await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
        await task

        assert isinstance(result, PermissionResultDeny)

    @pytest.mark.asyncio
    async def test_no_decision_defaults_to_deny(self, session: ChatSession) -> None:
        """If the event fires without a decision, ExitPlanMode should deny (fail closed)."""

        async def set_event_without_decision() -> None:
            """Simulate a race where the event is set but no decision was stored."""
            await asyncio.sleep(0.05)
            # Set the event directly without calling provide_plan_decision
            if session._pending_plan_event is not None:
                session._pending_plan_event.set()

        task = asyncio.create_task(set_event_without_decision())
        result = await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
        await task

        assert isinstance(result, PermissionResultDeny)
        assert "approval" in result.message.lower() or "review" in result.message.lower()

    @pytest.mark.asyncio
    async def test_timeout_returns_deny(self, session: ChatSession) -> None:
        """ExitPlanMode should deny on timeout."""
        from unittest.mock import patch

        with patch(
            "gobby.servers.chat_session_permissions.asyncio.wait_for",
            side_effect=TimeoutError,
        ):
            result = await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())

        assert isinstance(result, PermissionResultDeny)
        assert "timed out" in result.message.lower()

    @pytest.mark.asyncio
    async def test_approve_sets_accept_edits_mode(self, session: ChatSession) -> None:
        """After approval, chat_mode should transition to 'accept_edits'."""

        async def approve_after_delay() -> None:
            await asyncio.sleep(0.05)
            session.provide_plan_decision("approve")

        task = asyncio.create_task(approve_after_delay())
        await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
        await task

        assert session.chat_mode == "accept_edits"

    @pytest.mark.asyncio
    async def test_request_changes_stays_in_plan_mode(self, session: ChatSession) -> None:
        """After request_changes, chat_mode should remain 'plan'."""

        async def reject_after_delay() -> None:
            await asyncio.sleep(0.05)
            session.provide_plan_decision("request_changes")

        task = asyncio.create_task(reject_after_delay())
        await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
        await task

        assert session.chat_mode == "plan"

    @pytest.mark.asyncio
    async def test_reject_does_not_broadcast_plan_if_mode_changed(
        self, session: ChatSession
    ) -> None:
        """If user toggled away from plan during the wait, reject should NOT broadcast 'plan'."""
        mode_changes: list[tuple[str, str]] = []

        async def track_mode_change(mode: str, reason: str) -> None:
            mode_changes.append((mode, reason))

        session._on_mode_changed = track_mode_change

        async def toggle_then_reject() -> None:
            await asyncio.sleep(0.05)
            # Simulate user toggling to bypass via the web UI
            session.set_chat_mode("bypass")
            session.provide_plan_decision("request_changes")

        task = asyncio.create_task(toggle_then_reject())
        result = await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
        await task

        assert isinstance(result, PermissionResultDeny)
        # The reject path should NOT have broadcast ("plan", "plan_changes_requested")
        # because chat_mode was already changed to "bypass".
        assert ("plan", "plan_changes_requested") not in mode_changes

    @pytest.mark.asyncio
    async def test_mode_toggle_cancels_pending_exit_plan_mode(
        self, session: ChatSession
    ) -> None:
        """set_chat_mode + provide_plan_decision simulates _handle_set_mode cancellation."""

        async def cancel_via_mode_toggle() -> None:
            await asyncio.sleep(0.05)
            # Simulate what _handle_set_mode does when toggling away from plan
            session.set_chat_mode("bypass")
            if session.has_pending_plan:
                session.provide_plan_decision("request_changes")

        task = asyncio.create_task(cancel_via_mode_toggle())
        result = await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
        await task

        assert isinstance(result, PermissionResultDeny)
        # chat_mode should remain "bypass" — not reset to "plan"
        assert session.chat_mode == "bypass"
