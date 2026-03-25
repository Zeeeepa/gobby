"""Tests for ExitPlanMode permission handling and plan file resolution.

ExitPlanMode now always denies gracefully — plan approval is triggered
via PostToolUse when the agent writes to .gobby/plans/*.md. The SDK
handles ExitPlanMode as a CLI-internal tool, bypassing can_use_tool.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from claude_agent_sdk import PermissionResultDeny, ToolPermissionContext

from gobby.servers.chat_session import ChatSession

pytestmark = pytest.mark.unit


@pytest.fixture
def session() -> ChatSession:
    s = ChatSession(conversation_id="test-plan-perm")
    s.set_chat_mode("plan")
    return s


class TestExitPlanModeDecision:
    """ExitPlanMode should always deny gracefully.

    Plan approval is now triggered via PostToolUse when the agent writes
    a plan file to .gobby/plans/*.md, not via ExitPlanMode interception.
    The Claude Agent SDK handles ExitPlanMode as a CLI-internal tool,
    bypassing the can_use_tool callback entirely in web chat sessions.
    """

    @pytest.mark.asyncio
    async def test_exit_plan_mode_denies_without_plan_file(self, session: ChatSession) -> None:
        """ExitPlanMode should deny when no plan file exists."""
        with patch.object(session, "_read_plan_file", return_value=None):
            session._plan_file_path = None
            result = await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
        assert isinstance(result, PermissionResultDeny)
        assert "automatically" in result.message.lower() or "plan" in result.message.lower()

    @pytest.mark.asyncio
    async def test_exit_plan_mode_stays_in_plan(self, session: ChatSession) -> None:
        """ExitPlanMode deny should NOT change the chat mode."""
        assert session.chat_mode == "plan"
        with patch.object(session, "_read_plan_file", return_value=None):
            session._plan_file_path = None
            await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
        assert session.chat_mode == "plan"

    @pytest.mark.asyncio
    async def test_exit_plan_mode_does_not_block(self, session: ChatSession) -> None:
        """ExitPlanMode should return immediately (no blocking for approval)."""
        import time

        with patch.object(session, "_read_plan_file", return_value=None):
            session._plan_file_path = None
            start = time.monotonic()
            await session._can_use_tool("ExitPlanMode", {}, ToolPermissionContext())
            elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"ExitPlanMode took {elapsed:.2f}s — should be instant"


class TestReadPlanFileResolution:
    """_read_plan_file should resolve relative paths against project_path."""

    def test_relative_plan_file_resolved_against_project_path(self, tmp_path: Path) -> None:
        """A tracked relative plan file path should resolve against project_path."""
        plan_dir = tmp_path / ".gobby" / "plans"
        plan_dir.mkdir(parents=True)
        plan_file = plan_dir / "plan.md"
        plan_file.write_text("# My Plan\nDo the thing.", encoding="utf-8")

        session = ChatSession(conversation_id="test-resolve", project_path=str(tmp_path))
        session._plan_file_path = ".gobby/plans/plan.md"

        content = session._read_plan_file()
        assert content is not None
        assert "My Plan" in content

    def test_fallback_scan_uses_project_path(self, tmp_path: Path) -> None:
        """Fallback scan should find .gobby/plans/*.md relative to project_path."""
        plan_dir = tmp_path / ".gobby" / "plans"
        plan_dir.mkdir(parents=True)
        (plan_dir / "impl.md").write_text("# Implementation Plan", encoding="utf-8")

        session = ChatSession(conversation_id="test-scan", project_path=str(tmp_path))
        # No _plan_file_path tracked — should fall back to scanning

        content = session._read_plan_file()
        assert content is not None
        assert "Implementation Plan" in content

    def test_absolute_plan_file_works_regardless(self, tmp_path: Path) -> None:
        """An absolute tracked path should work even without project_path."""
        plan_dir = tmp_path / ".gobby" / "plans"
        plan_dir.mkdir(parents=True)
        plan_file = plan_dir / "plan.md"
        plan_file.write_text("# Absolute Plan", encoding="utf-8")

        session = ChatSession(conversation_id="test-abs")
        session._plan_file_path = str(plan_file)

        content = session._read_plan_file()
        assert content is not None
        assert "Absolute Plan" in content

    def test_no_plan_file_returns_none(self, tmp_path: Path) -> None:
        """Should return None when no plan file exists anywhere."""
        session = ChatSession(conversation_id="test-missing", project_path=str(tmp_path))

        # Mock Path.home to an empty temp dir so fallback scan doesn't
        # find real plan files in ~/.claude/plans/ etc.
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        with patch("pathlib.Path.home", return_value=fake_home):
            content = session._read_plan_file()
        assert content is None


class TestSetChatModePersistCallback:
    """set_chat_mode should fire _on_mode_persist callback."""

    def test_callback_fires_on_mode_change(self) -> None:
        """set_chat_mode should invoke _on_mode_persist with the new mode."""
        session = ChatSession(conversation_id="test-persist-cb")
        persisted: list[str] = []
        session._on_mode_persist = lambda mode: persisted.append(mode)

        session.set_chat_mode("bypass")
        session.set_chat_mode("plan")
        session.set_chat_mode("accept_edits")

        assert persisted == ["bypass", "plan", "accept_edits"]

    def test_callback_exception_is_swallowed(self) -> None:
        """Exceptions in _on_mode_persist should not propagate."""
        session = ChatSession(conversation_id="test-persist-err")

        def _explode(mode: str) -> None:
            raise RuntimeError("DB down")

        session._on_mode_persist = _explode
        # Should not raise
        session.set_chat_mode("bypass")
        assert session.chat_mode == "bypass"

    def test_no_callback_is_fine(self) -> None:
        """set_chat_mode should work without a persist callback."""
        session = ChatSession(conversation_id="test-persist-none")
        session.set_chat_mode("normal")
        assert session.chat_mode == "normal"
