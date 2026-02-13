"""Tests for TmuxPaneMonitor."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.registry import RunningAgent
from gobby.agents.tmux.pane_monitor import _RECENTLY_ENDED_TTL, TmuxPaneMonitor
from gobby.agents.tmux.session_manager import TmuxSessionInfo
from gobby.hooks.events import HookEvent, HookEventType

pytestmark = pytest.mark.unit


def _make_agent(
    run_id: str = "run-1",
    session_id: str = "sess-1",
    tmux_session_name: str | None = "gobby-agent-1",
) -> RunningAgent:
    return RunningAgent(
        run_id=run_id,
        session_id=session_id,
        parent_session_id="parent-1",
        mode="terminal",
        tmux_session_name=tmux_session_name,
    )


def _make_session_obj(
    session_id: str = "sess-1",
    external_id: str = "ext-1",
    source: str = "claude",
) -> MagicMock:
    s = MagicMock()
    s.id = session_id
    s.external_id = external_id
    s.source = source
    return s


@pytest.mark.asyncio
async def test_no_tmux_agents_noop() -> None:
    """When no agents have tmux_session_name, callback is never called."""
    callback = MagicMock()
    monitor = TmuxPaneMonitor(session_end_callback=callback, poll_interval=1.0)

    agent_no_tmux = _make_agent(tmux_session_name=None)

    with (
        patch(
            "gobby.agents.tmux.pane_monitor.TmuxSessionManager.list_sessions",
            return_value=[],
        ),
        patch(
            "gobby.agents.registry.get_running_agent_registry",
        ) as mock_registry,
    ):
        mock_registry.return_value.list_all.return_value = [agent_no_tmux]
        await monitor._check_panes()

    callback.assert_not_called()


@pytest.mark.asyncio
async def test_all_alive_noop() -> None:
    """When all agent tmux sessions are still alive, callback is never called."""
    callback = MagicMock()
    monitor = TmuxPaneMonitor(session_end_callback=callback, poll_interval=1.0)

    agent = _make_agent(tmux_session_name="gobby-agent-1")

    with (
        patch(
            "gobby.agents.tmux.pane_monitor.TmuxSessionManager.list_sessions",
            return_value=[TmuxSessionInfo(name="gobby-agent-1")],
        ),
        patch(
            "gobby.agents.registry.get_running_agent_registry",
        ) as mock_registry,
    ):
        mock_registry.return_value.list_all.return_value = [agent]
        await monitor._check_panes()

    callback.assert_not_called()


@pytest.mark.asyncio
async def test_dead_session_triggers_callback() -> None:
    """When a tmux session is gone, callback is called with correct HookEvent."""
    callback = MagicMock()
    monitor = TmuxPaneMonitor(session_end_callback=callback, poll_interval=1.0)

    agent = _make_agent(session_id="sess-dead", tmux_session_name="gobby-dead")
    session_obj = _make_session_obj(session_id="sess-dead", external_id="ext-dead", source="claude")

    with (
        patch(
            "gobby.agents.tmux.pane_monitor.TmuxSessionManager.list_sessions",
            return_value=[TmuxSessionInfo(name="gobby-alive")],
        ),
        patch(
            "gobby.agents.registry.get_running_agent_registry",
        ) as mock_registry,
        patch.object(monitor, "_lookup_session", return_value=session_obj),
    ):
        mock_registry.return_value.list_all.return_value = [agent]
        await monitor._check_panes()

    callback.assert_called_once()
    event: HookEvent = callback.call_args[0][0]
    assert event.event_type == HookEventType.SESSION_END
    assert event.session_id == "ext-dead"
    assert event.metadata["_platform_session_id"] == "sess-dead"
    assert event.metadata["_tmux_pane_death"] is True


@pytest.mark.asyncio
async def test_recently_ended_prevents_double_fire() -> None:
    """mark_recently_ended blocks re-fire for the same session."""
    callback = MagicMock()
    monitor = TmuxPaneMonitor(session_end_callback=callback, poll_interval=1.0)

    agent = _make_agent(session_id="sess-ended", tmux_session_name="gobby-ended")

    # Mark as recently ended
    monitor.mark_recently_ended("sess-ended")

    with (
        patch(
            "gobby.agents.tmux.pane_monitor.TmuxSessionManager.list_sessions",
            return_value=[],
        ),
        patch(
            "gobby.agents.registry.get_running_agent_registry",
        ) as mock_registry,
    ):
        mock_registry.return_value.list_all.return_value = [agent]
        await monitor._check_panes()

    callback.assert_not_called()


@pytest.mark.asyncio
async def test_recently_ended_expires() -> None:
    """Old entries get pruned; agent triggers callback normally after TTL."""
    callback = MagicMock()
    monitor = TmuxPaneMonitor(session_end_callback=callback, poll_interval=1.0)

    agent = _make_agent(session_id="sess-old", tmux_session_name="gobby-old")
    session_obj = _make_session_obj(session_id="sess-old", external_id="ext-old")

    # Insert an entry that's already expired
    monitor._recently_ended["sess-old"] = time.monotonic() - _RECENTLY_ENDED_TTL - 1

    with (
        patch(
            "gobby.agents.tmux.pane_monitor.TmuxSessionManager.list_sessions",
            return_value=[],
        ),
        patch(
            "gobby.agents.registry.get_running_agent_registry",
        ) as mock_registry,
        patch.object(monitor, "_lookup_session", return_value=session_obj),
    ):
        mock_registry.return_value.list_all.return_value = [agent]
        await monitor._check_panes()

    callback.assert_called_once()


@pytest.mark.asyncio
async def test_callback_exception_no_crash() -> None:
    """An error in callback doesn't prevent processing other agents."""
    callback = MagicMock(side_effect=RuntimeError("boom"))
    monitor = TmuxPaneMonitor(session_end_callback=callback, poll_interval=1.0)

    agent = _make_agent(session_id="sess-err", tmux_session_name="gobby-err")
    session_obj = _make_session_obj(session_id="sess-err")

    with (
        patch(
            "gobby.agents.tmux.pane_monitor.TmuxSessionManager.list_sessions",
            return_value=[],
        ),
        patch(
            "gobby.agents.registry.get_running_agent_registry",
        ) as mock_registry,
        patch.object(monitor, "_lookup_session", return_value=session_obj),
    ):
        mock_registry.return_value.list_all.return_value = [agent]
        # Should not raise
        await monitor._check_panes()

    # Callback was called but raised; session should still be marked recently ended
    assert "sess-err" in monitor._recently_ended


@pytest.mark.asyncio
async def test_tmux_error_no_crash() -> None:
    """list_sessions failure is logged, loop continues without crashing."""
    callback = MagicMock()
    monitor = TmuxPaneMonitor(session_end_callback=callback, poll_interval=1.0)

    with patch(
        "gobby.agents.tmux.pane_monitor.TmuxSessionManager.list_sessions",
        side_effect=OSError("tmux not found"),
    ):
        # Should not raise
        await monitor._check_panes()

    callback.assert_not_called()


@pytest.mark.asyncio
async def test_session_not_in_db_skipped() -> None:
    """If session is not found in DB, it's skipped but marked recently ended."""
    callback = MagicMock()
    monitor = TmuxPaneMonitor(session_end_callback=callback, poll_interval=1.0)

    agent = _make_agent(session_id="sess-nodb", tmux_session_name="gobby-nodb")

    with (
        patch(
            "gobby.agents.tmux.pane_monitor.TmuxSessionManager.list_sessions",
            return_value=[],
        ),
        patch(
            "gobby.agents.registry.get_running_agent_registry",
        ) as mock_registry,
        patch.object(monitor, "_lookup_session", return_value=None),
    ):
        mock_registry.return_value.list_all.return_value = [agent]
        await monitor._check_panes()

    callback.assert_not_called()
    # Should still be marked to avoid re-logging every poll
    assert "sess-nodb" in monitor._recently_ended


@pytest.mark.asyncio
async def test_start_stop_lifecycle() -> None:
    """start() creates a task, stop() cancels it cleanly."""
    callback = MagicMock()
    monitor = TmuxPaneMonitor(session_end_callback=callback, poll_interval=100.0)

    await monitor.start()
    assert monitor._task is not None
    assert not monitor._task.done()

    await monitor.stop()
    assert monitor._task is None
