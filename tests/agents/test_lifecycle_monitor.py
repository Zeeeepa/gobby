"""Tests for gobby.agents.lifecycle_monitor module.

Tests for the AgentLifecycleMonitor that detects dead tmux sessions
and completed/failed autonomous tasks, and marks their agent DB records.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.agents.lifecycle_monitor import AgentLifecycleMonitor
from gobby.agents.registry import RunningAgent, RunningAgentRegistry
from gobby.storage.agents import LocalAgentRunManager
from gobby.storage.database import LocalDatabase
from gobby.storage.sessions import LocalSessionManager

pytestmark = pytest.mark.unit


@pytest.fixture
def registry() -> RunningAgentRegistry:
    """Registry fixture retained for test helpers that still populate it.

    The lifecycle monitor itself no longer reads from the registry (DB-driven),
    but some test helpers still use it to set up in-memory state for assertions.
    TODO: Remove once all tests are migrated to DB-only setup.
    """
    return RunningAgentRegistry()


@pytest.fixture
def agent_run_manager(temp_db: LocalDatabase) -> LocalAgentRunManager:
    return LocalAgentRunManager(temp_db)


@pytest.fixture
def sample_session(
    session_manager: LocalSessionManager,
    sample_project: dict,
) -> dict:
    session = session_manager.register(
        external_id="lifecycle-test-session",
        machine_id="machine-1",
        source="claude",
        project_id=sample_project["id"],
    )
    return session.to_dict()


@pytest.fixture
def monitor(
    agent_run_manager: LocalAgentRunManager,
    temp_db: LocalDatabase,
) -> AgentLifecycleMonitor:
    return AgentLifecycleMonitor(
        agent_run_manager=agent_run_manager,
        db=temp_db,
        check_interval_seconds=1.0,
    )


def _make_terminal_agent(
    registry: RunningAgentRegistry,
    run_id: str = "run-abc123",
    session_id: str = "sess-child",
    parent_session_id: str = "sess-parent",
    tmux_session_name: str = "gobby-1234567890-abc123",
) -> RunningAgent:
    """Helper to create and register a terminal-mode agent."""
    agent = RunningAgent(
        run_id=run_id,
        session_id=session_id,
        parent_session_id=parent_session_id,
        mode="terminal",
        tmux_session_name=tmux_session_name,
        started_at=datetime.now(UTC),
    )
    registry.add(agent)
    return agent


def _make_autonomous_agent(
    registry: RunningAgentRegistry,
    run_id: str = "run-auto",
    session_id: str = "sess-auto",
    parent_session_id: str = "sess-parent",
    task: asyncio.Task | None = None,  # type: ignore[type-arg]
) -> RunningAgent:
    """Helper to create and register an autonomous-mode agent with an asyncio.Task."""
    agent = RunningAgent(
        run_id=run_id,
        session_id=session_id,
        parent_session_id=parent_session_id,
        mode="autonomous",
        started_at=datetime.now(UTC),
        task=task,
    )
    registry.add(agent)
    return agent


class TestCheckDeadAgents:
    """Tests for check_unhealthy_agents."""

    @pytest.mark.asyncio
    async def test_detects_dead_tmux_session(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Dead tmux session is detected and agent run marked as failed."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-dead",
        )
        agent_run_manager.start(run.id)
        _make_terminal_agent(registry, run_id=run.id, tmux_session_name="gobby-dead")

        with patch.object(monitor._tmux, "has_session", new_callable=AsyncMock, return_value=False):
            cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 1
        assert registry.get(run.id) is None

        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "error"
        assert "tmux session died" in (updated.error or "")

    @pytest.mark.asyncio
    async def test_skips_alive_tmux_session(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Alive tmux session is left untouched."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-alive",
        )
        agent_run_manager.start(run.id)
        _make_terminal_agent(registry, run_id=run.id, tmux_session_name="gobby-alive")

        with patch.object(monitor._tmux, "has_session", new_callable=AsyncMock, return_value=True):
            cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 0
        assert registry.get(run.id) is not None

        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "running"

    @pytest.mark.asyncio
    async def test_no_tmux_agents_returns_zero(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """Returns 0 when no terminal agents are in the registry."""
        cleaned = await monitor.check_unhealthy_agents()
        assert cleaned == 0

    @pytest.mark.asyncio
    async def test_skips_non_terminal_agents(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Non-terminal agents (autonomous, in_process) are not checked."""
        agent = RunningAgent(
            run_id="run-autonomous",
            session_id="sess-1",
            parent_session_id="sess-parent",
            mode="autonomous",
            tmux_session_name=None,
        )
        registry.add(agent)

        cleaned = await monitor.check_unhealthy_agents()
        assert cleaned == 0
        assert registry.get("run-autonomous") is not None

    @pytest.mark.asyncio
    async def test_skips_already_completed_db_record(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """If DB record is already in terminal state, only cleans registry."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-done",
        )
        agent_run_manager.start(run.id)
        agent_run_manager.complete(run.id, result="done")
        _make_terminal_agent(registry, run_id=run.id, tmux_session_name="gobby-done")

        with patch.object(monitor._tmux, "has_session", new_callable=AsyncMock, return_value=False):
            cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 1
        assert registry.get(run.id) is None
        # DB status should remain 'success', not overwritten
        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "success"

    @pytest.mark.asyncio
    async def test_handles_tmux_check_error(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Errors checking tmux are caught per-agent, don't crash the loop."""
        _make_terminal_agent(registry, run_id="run-err", tmux_session_name="gobby-err")

        with patch.object(
            monitor._tmux,
            "has_session",
            new_callable=AsyncMock,
            side_effect=OSError("tmux socket gone"),
        ):
            cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 0
        # Agent stays in registry since we couldn't determine its status
        assert registry.get("run-err") is not None

    @pytest.mark.asyncio
    async def test_releases_worktrees_on_dead_agent(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Worktrees are released when a dead agent is cleaned up."""
        mock_coordinator = MagicMock()
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            session_coordinator=mock_coordinator,
        )

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-wt",
        )
        agent_run_manager.start(run.id)
        agent = _make_terminal_agent(
            registry, run_id=run.id, session_id="sess-wt", tmux_session_name="gobby-wt"
        )

        with patch.object(mon._tmux, "has_session", new_callable=AsyncMock, return_value=False):
            await mon.check_unhealthy_agents()

        mock_coordinator.release_session_worktrees.assert_called_once_with(agent.session_id)


class TestCheckDeadAutonomousAgents:
    """Tests for autonomous/in_process task-based agent detection in check_unhealthy_agents."""

    @pytest.mark.asyncio
    async def test_detects_completed_autonomous_task(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Completed autonomous task is detected and agent run marked as success."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-auto-done",
        )
        agent_run_manager.start(run.id)

        # Create a done task (completed successfully)
        async def _ok() -> str:
            return "result"

        done_task: asyncio.Task[str] = asyncio.ensure_future(_ok())
        await done_task  # Let it finish

        _make_autonomous_agent(registry, run_id=run.id, task=done_task)

        cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 1
        assert registry.get(run.id) is None

        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "success"

    @pytest.mark.asyncio
    async def test_detects_failed_autonomous_task(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Failed autonomous task is detected and agent run marked as error."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-auto-fail",
        )
        agent_run_manager.start(run.id)

        # Create a done task that raised an exception
        async def _failing() -> str:
            raise RuntimeError("SDK connection lost")

        failed_task: asyncio.Task[str] = asyncio.ensure_future(_failing())
        try:
            await failed_task
        except RuntimeError:
            pass

        _make_autonomous_agent(registry, run_id=run.id, task=failed_task)

        cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 1
        assert registry.get(run.id) is None

        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "error"
        assert "SDK connection lost" in (updated.error or "")

    @pytest.mark.asyncio
    async def test_detects_cancelled_autonomous_task(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Cancelled autonomous task is detected and cleaned up."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-auto-cancel",
        )
        agent_run_manager.start(run.id)

        # Create a cancelled task
        async def _hang() -> str:
            await asyncio.sleep(3600)
            return "never"

        cancel_task: asyncio.Task[str] = asyncio.ensure_future(_hang())
        cancel_task.cancel()
        try:
            await cancel_task
        except asyncio.CancelledError:
            pass

        _make_autonomous_agent(registry, run_id=run.id, task=cancel_task)

        cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 1
        assert registry.get(run.id) is None

        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "error"
        assert "cancelled" in (updated.error or "").lower()

    @pytest.mark.asyncio
    async def test_skips_still_running_autonomous_task(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Still-running autonomous tasks are left untouched."""

        async def _long_running() -> str:
            await asyncio.sleep(3600)
            return "done"

        running_task: asyncio.Task[str] = asyncio.ensure_future(_long_running())
        _make_autonomous_agent(registry, run_id="run-still-going", task=running_task)

        cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 0
        assert registry.get("run-still-going") is not None
        running_task.cancel()
        try:
            await running_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_autonomous_agent_without_task_is_skipped(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Autonomous agents with no task field are skipped."""
        _make_autonomous_agent(registry, run_id="run-no-task", task=None)

        cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 0
        assert registry.get("run-no-task") is not None

    @pytest.mark.asyncio
    async def test_releases_worktrees_on_completed_autonomous(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Worktrees are released when a completed autonomous agent is cleaned up."""
        mock_coordinator = MagicMock()
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            session_coordinator=mock_coordinator,
        )

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-auto-wt",
        )
        agent_run_manager.start(run.id)

        async def _ok2() -> str:
            return "ok"

        done_task: asyncio.Task[str] = asyncio.ensure_future(_ok2())
        await done_task

        agent = _make_autonomous_agent(
            registry, run_id=run.id, session_id="sess-auto-wt", task=done_task
        )

        cleaned = await mon.check_unhealthy_agents()

        assert cleaned == 1
        mock_coordinator.release_session_worktrees.assert_called_once_with(agent.session_id)

    @pytest.mark.asyncio
    async def test_releases_clones_on_failed_autonomous(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Clones are released when a failed autonomous agent is cleaned up."""
        mock_clone_storage = MagicMock()
        mock_clone_storage.release = MagicMock()  # Sync method, called via to_thread
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            clone_storage=mock_clone_storage,
        )

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-auto-clone",
        )
        agent_run_manager.start(run.id)

        async def _failing() -> str:
            raise ValueError("boom")

        failed_task: asyncio.Task[str] = asyncio.ensure_future(_failing())
        try:
            await failed_task
        except ValueError:
            pass

        agent = RunningAgent(
            run_id=run.id,
            session_id="sess-auto-clone",
            parent_session_id="sess-parent",
            mode="autonomous",
            started_at=datetime.now(UTC),
            task=failed_task,
            clone_id="clone-123",
        )
        registry.add(agent)

        cleaned = await mon.check_unhealthy_agents()

        assert cleaned == 1
        mock_clone_storage.release.assert_called_once_with("clone-123")


class TestRecoverOrCleanupAgents:
    """Tests for recover_or_cleanup_agents (post-restart recovery)."""

    @pytest.mark.asyncio
    async def test_cleans_dead_agents(
        self,
        monitor: AgentLifecycleMonitor,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Running DB records with no live process/tmux are marked as failed."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-orphan",
        )
        agent_run_manager.start(run.id)
        # No PID or tmux_session_name set — both checks will be false

        recovered, cleaned = await monitor.recover_or_cleanup_agents()

        assert recovered == 0
        assert cleaned == 1
        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "error"
        assert "Orphaned" in (updated.error or "")

    @pytest.mark.asyncio
    async def test_recovers_alive_agents(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Running DB records with live process+tmux are recovered to registry."""
        import os

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-alive",
        )
        agent_run_manager.start(run.id)
        # Set runtime state: use current process PID (guaranteed alive)
        agent_run_manager.update_runtime(
            run.id,
            pid=os.getpid(),
            tmux_session_name="gobby-alive-test",
            mode="terminal",
        )

        # Mock tmux has_session to return True
        monitor._tmux.has_session = AsyncMock(return_value=True)  # type: ignore[assignment]

        recovered, cleaned = await monitor.recover_or_cleanup_agents()

        assert recovered == 1
        assert cleaned == 0
        # Agent should be in the in-memory registry
        agent = registry.get(run.id)
        assert agent is not None
        assert agent.pid == os.getpid()

    @pytest.mark.asyncio
    async def test_no_running_runs_returns_zeros(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """Returns (0, 0) when there are no running DB records."""
        recovered, cleaned = await monitor.recover_or_cleanup_agents()
        assert recovered == 0
        assert cleaned == 0


class TestStartStop:
    """Tests for monitor start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_task(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """start() creates a background asyncio task."""
        await monitor.start()
        try:
            assert monitor._task is not None
            assert not monitor._task.done()
        finally:
            await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """stop() cancels the background task."""
        await monitor.start()
        await monitor.stop()
        assert monitor._task is None

    @pytest.mark.asyncio
    async def test_double_start_is_noop(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """Calling start() twice doesn't create duplicate tasks."""
        await monitor.start()
        task1 = monitor._task
        await monitor.start()
        task2 = monitor._task
        assert task1 is task2
        await monitor.stop()


class TestCheckIdleAgents:
    """Tests for idle agent detection and reprompting."""

    @pytest.fixture
    def idle_monitor(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
    ) -> AgentLifecycleMonitor:
        from gobby.config.tmux import TmuxConfig

        config = TmuxConfig(
            idle_check_enabled=True, idle_timeout_seconds=10, max_reprompt_attempts=2
        )
        return AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            check_interval_seconds=1.0,
            tmux_config=config,
        )

    @pytest.mark.asyncio
    async def test_active_agent_not_touched(
        self,
        idle_monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Active agents should not be reprompted."""
        _make_terminal_agent(registry, run_id="run-active", tmux_session_name="gobby-active")

        with patch.object(
            idle_monitor._tmux,
            "capture_pane",
            new_callable=AsyncMock,
            return_value="Running tests...\n",
        ):
            handled = await idle_monitor.check_idle_agents()

        assert handled == 0

    @pytest.mark.asyncio
    async def test_idle_agent_reprompted(
        self,
        idle_monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Idle agent past timeout should be reprompted."""
        import time

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-idle",
        )
        agent_run_manager.start(run.id)
        _make_terminal_agent(registry, run_id=run.id, tmux_session_name="gobby-idle")

        # Pre-set idle state to simulate timeout elapsed
        state = idle_monitor._idle_detector.get_state(run.id)
        state.first_idle_at = time.monotonic() - 120

        with (
            patch.object(
                idle_monitor._tmux, "capture_pane", new_callable=AsyncMock, return_value="❯\n"
            ),
            patch.object(
                idle_monitor._tmux, "send_keys", new_callable=AsyncMock, return_value=True
            ) as mock_send,
        ):
            handled = await idle_monitor.check_idle_agents()

        assert handled == 1
        mock_send.assert_called_once()
        assert "Continue working" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_idle_agent_failed_after_max_reprompts(
        self,
        idle_monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Agent should be failed after exhausting reprompt attempts."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-exhausted",
        )
        agent_run_manager.start(run.id)
        _make_terminal_agent(registry, run_id=run.id, tmux_session_name="gobby-exhausted")

        # Set reprompt count at max
        state = idle_monitor._idle_detector.get_state(run.id)
        state.reprompt_count = 2  # max_reprompt_attempts = 2

        with (
            patch.object(
                idle_monitor._tmux, "capture_pane", new_callable=AsyncMock, return_value="❯\n"
            ),
            patch.object(
                idle_monitor._tmux, "kill_session", new_callable=AsyncMock, return_value=True
            ),
        ):
            handled = await idle_monitor.check_idle_agents()

        assert handled == 1
        assert registry.get(run.id) is None
        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "error"
        assert "idle" in (updated.error or "").lower()

    @pytest.mark.asyncio
    async def test_context_full_fails_immediately(
        self,
        idle_monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Context-full agent should be failed immediately without reprompt."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-ctx-full",
        )
        agent_run_manager.start(run.id)
        _make_terminal_agent(registry, run_id=run.id, tmux_session_name="gobby-ctx")

        with (
            patch.object(
                idle_monitor._tmux,
                "capture_pane",
                new_callable=AsyncMock,
                return_value="The context window is full.\n❯\n",
            ),
            patch.object(
                idle_monitor._tmux, "kill_session", new_callable=AsyncMock, return_value=True
            ),
        ):
            handled = await idle_monitor.check_idle_agents()

        assert handled == 1
        assert registry.get(run.id) is None
        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "error"
        assert "context" in (updated.error or "").lower()

    @pytest.mark.asyncio
    async def test_disabled_idle_check(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
    ) -> None:
        """Idle check should be skipped when disabled."""
        from gobby.config.tmux import TmuxConfig

        config = TmuxConfig(idle_check_enabled=False)
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            tmux_config=config,
        )
        _make_terminal_agent(registry, run_id="run-skip", tmux_session_name="gobby-skip")

        handled = await mon.check_idle_agents()
        assert handled == 0

    @pytest.mark.asyncio
    async def test_capture_pane_failure_skipped(
        self,
        idle_monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Agent should be skipped if capture_pane returns None."""
        _make_terminal_agent(registry, run_id="run-no-capture", tmux_session_name="gobby-nocap")

        with patch.object(
            idle_monitor._tmux, "capture_pane", new_callable=AsyncMock, return_value=None
        ):
            handled = await idle_monitor.check_idle_agents()

        assert handled == 0


class TestCheckTrustPrompts:
    """Tests for trust prompt detection and auto-dismissal."""

    @pytest.mark.asyncio
    async def test_sends_dismiss_key_on_trust_prompt(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Trust prompt detected -> sends Enter to dismiss."""
        _make_terminal_agent(registry, run_id="run-trust", tmux_session_name="gobby-trust")

        trust_output = (
            "Do you trust the files in this folder?\n"
            "1. Trust Folder\n"
            "2. Trust parent Folder\n"
            "3. Don't Trust\n"
        )

        with (
            patch.object(
                monitor._tmux,
                "capture_pane",
                new_callable=AsyncMock,
                return_value=trust_output,
            ),
            patch.object(
                monitor._tmux, "send_keys", new_callable=AsyncMock, return_value=True
            ) as mock_send,
        ):
            handled = await monitor.check_trust_prompts()

        assert handled == 1
        mock_send.assert_called_once_with("gobby-trust", "\n")

    @pytest.mark.asyncio
    async def test_no_action_on_normal_output(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Normal agent output does not trigger trust dismissal."""
        _make_terminal_agent(registry, run_id="run-normal", tmux_session_name="gobby-normal")

        with (
            patch.object(
                monitor._tmux,
                "capture_pane",
                new_callable=AsyncMock,
                return_value="Running tests...\n",
            ),
            patch.object(monitor._tmux, "send_keys", new_callable=AsyncMock) as mock_send,
        ):
            handled = await monitor.check_trust_prompts()

        assert handled == 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_dismiss_twice(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """After dismissal, the same agent is not dismissed again."""
        _make_terminal_agent(registry, run_id="run-once", tmux_session_name="gobby-once")

        trust_output = "Do you trust the files in this folder?\n"

        with (
            patch.object(
                monitor._tmux,
                "capture_pane",
                new_callable=AsyncMock,
                return_value=trust_output,
            ),
            patch.object(
                monitor._tmux, "send_keys", new_callable=AsyncMock, return_value=True
            ) as mock_send,
        ):
            # First call should dismiss
            handled1 = await monitor.check_trust_prompts()
            # Second call should skip (already dismissed)
            handled2 = await monitor.check_trust_prompts()

        assert handled1 == 1
        assert handled2 == 0
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_non_terminal_agents(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Non-terminal agents are not checked for trust prompts."""
        _make_autonomous_agent(registry, run_id="run-auto-trust")

        handled = await monitor.check_trust_prompts()
        assert handled == 0

    @pytest.mark.asyncio
    async def test_skips_when_capture_pane_fails(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Agent is skipped if capture_pane returns None."""
        _make_terminal_agent(registry, run_id="run-nocap", tmux_session_name="gobby-nocap")

        with patch.object(monitor._tmux, "capture_pane", new_callable=AsyncMock, return_value=None):
            handled = await monitor.check_trust_prompts()

        assert handled == 0

    @pytest.mark.asyncio
    async def test_cleared_on_dead_agent_cleanup(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Prompt detector state is cleared when a dead agent is cleaned up."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-cleanup",
        )
        agent_run_manager.start(run.id)
        _make_terminal_agent(registry, run_id=run.id, tmux_session_name="gobby-cleanup")

        # Pre-mark as dismissed
        monitor._prompt_detector.mark_dismissed(run.id)

        with patch.object(monitor._tmux, "has_session", new_callable=AsyncMock, return_value=False):
            await monitor.check_unhealthy_agents()

        # State should be cleared after cleanup
        assert monitor._prompt_detector.was_dismissed(run.id) is False


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


class TestCheckExpiredAgents:
    """Tests for check_unhealthy_agents."""

    @pytest.mark.asyncio
    async def test_no_agents_returns_zero(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """Returns 0 when no agents in registry."""
        cleaned = await monitor.check_unhealthy_agents()
        assert cleaned == 0

    @pytest.mark.asyncio
    async def test_agent_without_timeout_skipped(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Agents without timeout set are not killed by timeout check."""
        agent = RunningAgent(
            run_id="run-no-timeout",
            session_id="sess-1",
            parent_session_id="sess-parent",
            mode="terminal",
            tmux_session_name="gobby-no-timeout",
            timeout_seconds=None,
        )
        registry.add(agent)
        with patch.object(monitor._tmux, "has_session", new_callable=AsyncMock, return_value=True):
            cleaned = await monitor.check_unhealthy_agents()
        assert cleaned == 0

    @pytest.mark.asyncio
    async def test_agent_within_timeout_skipped(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Agents within their timeout are not killed."""
        agent = RunningAgent(
            run_id="run-not-expired",
            session_id="sess-1",
            parent_session_id="sess-parent",
            mode="terminal",
            tmux_session_name="gobby-not-expired",
            started_at=datetime.now(UTC),
            timeout_seconds=3600,
        )
        registry.add(agent)
        with patch.object(monitor._tmux, "has_session", new_callable=AsyncMock, return_value=True):
            cleaned = await monitor.check_unhealthy_agents()
        assert cleaned == 0

    @pytest.mark.asyncio
    async def test_expired_agent_killed(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Expired agent is killed and marked as failed."""
        from datetime import timedelta

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-expired",
        )
        agent_run_manager.start(run.id)

        agent = RunningAgent(
            run_id=run.id,
            session_id="sess-expired",
            parent_session_id=sample_session["id"],
            mode="terminal",
            tmux_session_name="gobby-expired",
            started_at=datetime.now(UTC) - timedelta(seconds=600),
            timeout_seconds=300,
        )
        registry.add(agent)

        with patch.object(registry, "kill", new_callable=AsyncMock, return_value={"killed": True}):
            cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 1
        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "error"
        assert "timeout" in (updated.error or "").lower()

    @pytest.mark.asyncio
    async def test_expired_agent_releases_worktrees(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Expired agent cleanup releases worktrees."""
        from datetime import timedelta

        mock_coordinator = MagicMock()
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            session_coordinator=mock_coordinator,
        )

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-exp-wt",
        )
        agent_run_manager.start(run.id)

        agent = RunningAgent(
            run_id=run.id,
            session_id="sess-exp-wt",
            parent_session_id=sample_session["id"],
            mode="terminal",
            tmux_session_name="gobby-exp-wt",
            started_at=datetime.now(UTC) - timedelta(seconds=600),
            timeout_seconds=300,
        )
        registry.add(agent)

        with patch.object(registry, "kill", new_callable=AsyncMock, return_value={"killed": True}):
            await mon.check_unhealthy_agents()

        mock_coordinator.release_session_worktrees.assert_called_once_with(agent.session_id)

    @pytest.mark.asyncio
    async def test_expired_agent_releases_clones(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Expired agent cleanup releases clones."""
        from datetime import timedelta

        mock_clone_storage = MagicMock()
        mock_clone_storage.release = MagicMock()
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            clone_storage=mock_clone_storage,
        )

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-exp-cl",
        )
        agent_run_manager.start(run.id)

        agent = RunningAgent(
            run_id=run.id,
            session_id="sess-exp-cl",
            parent_session_id=sample_session["id"],
            mode="terminal",
            tmux_session_name="gobby-exp-cl",
            started_at=datetime.now(UTC) - timedelta(seconds=600),
            timeout_seconds=300,
            clone_id="clone-456",
        )
        registry.add(agent)

        with patch.object(registry, "kill", new_callable=AsyncMock, return_value={"killed": True}):
            await mon.check_unhealthy_agents()

        mock_clone_storage.release.assert_called_once_with("clone-456")


class TestCheckProviderStalls:
    """Tests for check_provider_stalls."""

    @pytest.mark.asyncio
    async def test_no_agents_returns_zero(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """Returns 0 when no agents in registry."""
        stalled = await monitor.check_provider_stalls()
        assert stalled == 0

    @pytest.mark.asyncio
    async def test_healthy_agent_not_counted(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Healthy agent is not counted as stalled."""
        _make_terminal_agent(registry, run_id="run-healthy", tmux_session_name="gobby-healthy")

        with patch.object(
            monitor._tmux,
            "capture_pane",
            new_callable=AsyncMock,
            return_value="Working on task...\n",
        ):
            stalled = await monitor.check_provider_stalls()

        assert stalled == 0

    @pytest.mark.asyncio
    async def test_capture_pane_error_handled(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Error during capture_pane is handled gracefully."""
        _make_terminal_agent(registry, run_id="run-stall-err", tmux_session_name="gobby-stall-err")

        with patch.object(
            monitor._tmux,
            "capture_pane",
            new_callable=AsyncMock,
            side_effect=OSError("tmux error"),
        ):
            stalled = await monitor.check_provider_stalls()

        assert stalled == 0


class TestCheckLoopPrompts:
    """Tests for loop prompt detection and auto-dismissal."""

    @pytest.mark.asyncio
    async def test_dismisses_loop_prompt(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Loop prompt is dismissed by sending keys."""
        _make_terminal_agent(registry, run_id="run-loop", tmux_session_name="gobby-loop")

        loop_output = "It looks like you may be stuck in a loop. Continue? (y/n)\n"

        with (
            patch.object(
                monitor._tmux,
                "capture_pane",
                new_callable=AsyncMock,
                return_value=loop_output,
            ),
            patch.object(
                monitor._tmux, "send_keys", new_callable=AsyncMock, return_value=True
            ) as mock_send,
            patch.object(
                monitor._prompt_detector,
                "detect_loop_prompt",
                return_value=True,
            ),
        ):
            handled = await monitor.check_loop_prompts()

        assert handled == 1
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_loop_prompt(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Normal output does not trigger loop prompt dismissal."""
        _make_terminal_agent(registry, run_id="run-noloop", tmux_session_name="gobby-noloop")

        with (
            patch.object(
                monitor._tmux,
                "capture_pane",
                new_callable=AsyncMock,
                return_value="Working...\n",
            ),
            patch.object(monitor._tmux, "send_keys", new_callable=AsyncMock) as mock_send,
        ):
            handled = await monitor.check_loop_prompts()

        assert handled == 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_non_terminal_agents(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Non-terminal agents are skipped for loop prompt check."""
        _make_autonomous_agent(registry, run_id="run-auto-loop")
        handled = await monitor.check_loop_prompts()
        assert handled == 0

    @pytest.mark.asyncio
    async def test_error_during_loop_check(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
    ) -> None:
        """Error during loop prompt check is handled gracefully."""
        _make_terminal_agent(registry, run_id="run-loop-err", tmux_session_name="gobby-loop-err")

        with patch.object(
            monitor._tmux,
            "capture_pane",
            new_callable=AsyncMock,
            side_effect=OSError("tmux gone"),
        ):
            handled = await monitor.check_loop_prompts()

        assert handled == 0


class TestRecoverTaskFromFailedAgent:
    """Tests for _recover_task_from_failed_agent."""

    @pytest.mark.asyncio
    async def test_no_task_manager_is_noop(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
    ) -> None:
        """Without task_manager, recovery does nothing."""
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            task_manager=None,
        )
        # Should not raise
        await mon._recover_task_from_failed_agent("nonexistent-run")

    @pytest.mark.asyncio
    async def test_no_db_run_is_noop(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
    ) -> None:
        """When DB run not found, recovery does nothing."""
        mock_task_manager = MagicMock()
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            task_manager=mock_task_manager,
        )
        await mon._recover_task_from_failed_agent("nonexistent-run")
        mock_task_manager.update_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_recover_task_from_registry_fallback(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Task ID from in-memory registry is used when DB run has no task_id."""
        mock_task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task.seq_num = 1
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []

        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            task_manager=mock_task_manager,
        )

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-recov-reg",
        )
        agent_run_manager.start(run.id)

        # Register agent with task_id in registry
        agent = RunningAgent(
            run_id=run.id,
            session_id="sess-recov",
            parent_session_id=sample_session["id"],
            mode="terminal",
            task_id="task-from-registry",
        )
        registry.add(agent)

        await mon._recover_task_from_failed_agent(run.id)

        mock_task_manager.update_task.assert_called_once_with(
            "task-from-registry", status="open", assignee=None
        )


class TestSetSessionCoordinator:
    """Tests for set_session_coordinator."""

    def test_sets_coordinator(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """set_session_coordinator updates the coordinator reference."""
        mock_coordinator = MagicMock()
        monitor.set_session_coordinator(mock_coordinator)
        assert monitor._session_coordinator is mock_coordinator


class TestCleanupStalePendingRuns:
    """Tests for cleanup_stale_pending_runs."""

    @pytest.mark.asyncio
    async def test_delegates_to_agent_run_manager(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """cleanup_stale_pending_runs delegates to agent_run_manager."""
        with patch.object(
            monitor._agent_run_manager,
            "cleanup_stale_pending_runs",
            return_value=3,
        ):
            result = await monitor.cleanup_stale_pending_runs()
        assert result == 3


class TestFireOrphanCompletion:
    """Tests for _fire_orphan_completion."""

    @pytest.mark.asyncio
    async def test_no_completion_registry_is_noop(
        self,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """Without completion_registry, nothing happens."""
        assert monitor._completion_registry is None
        # Should not raise
        await monitor._fire_orphan_completion("run-123")

    @pytest.mark.asyncio
    async def test_fires_with_unregistered_run(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
    ) -> None:
        """Registers and notifies for an unregistered run."""
        mock_cr = MagicMock()
        mock_cr.is_registered.return_value = False
        mock_cr.notify = AsyncMock()
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            completion_registry=mock_cr,
        )
        await mon._fire_orphan_completion("run-orphan")
        mock_cr.register.assert_called_once()
        mock_cr.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_fires_with_already_registered_run(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
    ) -> None:
        """Notifies without re-registering an already registered run."""
        mock_cr = MagicMock()
        mock_cr.is_registered.return_value = True
        mock_cr.notify = AsyncMock()
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            completion_registry=mock_cr,
        )
        await mon._fire_orphan_completion("run-registered")
        mock_cr.register.assert_not_called()
        mock_cr.notify.assert_called_once()


class TestDeadAgentCompletionEvent:
    """Tests for completion event firing in check_unhealthy_agents."""

    @pytest.mark.asyncio
    async def test_fires_completion_on_dead_tmux_agent(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Completion event is fired when a dead tmux agent is cleaned up."""
        mock_cr = MagicMock()
        mock_cr.notify = AsyncMock()
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            completion_registry=mock_cr,
        )

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-dead-cr",
        )
        agent_run_manager.start(run.id)
        _make_terminal_agent(registry, run_id=run.id, tmux_session_name="gobby-dead-cr")

        with patch.object(mon._tmux, "has_session", new_callable=AsyncMock, return_value=False):
            await mon.check_unhealthy_agents()

        mock_cr.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_releases_clones_on_dead_tmux_agent(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """Clones are released when a dead tmux agent with clone_id is cleaned up."""
        mock_clone_storage = MagicMock()
        mock_clone_storage.release = MagicMock()
        mon = AgentLifecycleMonitor(
            agent_registry=registry,
            agent_run_manager=agent_run_manager,
            clone_storage=mock_clone_storage,
        )

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-dead-clone",
        )
        agent_run_manager.start(run.id)

        agent = RunningAgent(
            run_id=run.id,
            session_id="sess-dead-clone",
            parent_session_id=sample_session["id"],
            mode="terminal",
            tmux_session_name="gobby-dead-clone",
            started_at=datetime.now(UTC),
            clone_id="clone-789",
        )
        registry.add(agent)

        with patch.object(mon._tmux, "has_session", new_callable=AsyncMock, return_value=False):
            await mon.check_unhealthy_agents()

        mock_clone_storage.release.assert_called_once_with("clone-789")


class TestDeadAgentKillsOrphanedProcess:
    """Tests for killing orphaned processes in check_unhealthy_agents."""

    @pytest.mark.asyncio
    async def test_kills_orphaned_process(
        self,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
        monitor: AgentLifecycleMonitor,
    ) -> None:
        """Orphaned process receives SIGTERM when tmux is dead."""
        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-orphan-pid",
        )
        agent_run_manager.start(run.id)

        agent = RunningAgent(
            run_id=run.id,
            session_id="sess-orphan-pid",
            parent_session_id=sample_session["id"],
            mode="terminal",
            tmux_session_name="gobby-orphan-pid",
            started_at=datetime.now(UTC),
            pid=999999,  # Non-existent PID
        )
        registry.add(agent)

        with patch.object(monitor._tmux, "has_session", new_callable=AsyncMock, return_value=False):
            cleaned = await monitor.check_unhealthy_agents()

        assert cleaned == 1


class TestRecoverOrCleanupPidAliveNoTmux:
    """Tests for recover_or_cleanup_agents when PID alive but tmux dead."""

    @pytest.mark.asyncio
    async def test_kills_orphan_when_pid_alive_tmux_dead(
        self,
        monitor: AgentLifecycleMonitor,
        registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        sample_session: dict,
    ) -> None:
        """When PID is alive but tmux is dead, the process is killed."""
        import os

        run = agent_run_manager.create(
            parent_session_id=sample_session["id"],
            provider="claude",
            prompt="test",
            run_id="run-pid-no-tmux",
        )
        agent_run_manager.start(run.id)
        agent_run_manager.update_runtime(
            run.id,
            pid=os.getpid(),
            tmux_session_name="gobby-dead-tmux",
            mode="terminal",
        )

        # PID alive (current process), tmux dead
        with (
            patch.object(monitor._tmux, "has_session", new_callable=AsyncMock, return_value=False),
            patch("os.kill") as mock_kill,
        ):
            recovered, cleaned = await monitor.recover_or_cleanup_agents()

        assert recovered == 0
        assert cleaned == 1
        # os.kill called twice: once with signal 0 (alive check), once with SIGTERM (kill)
        assert mock_kill.call_count == 2
        import signal

        mock_kill.assert_any_call(os.getpid(), signal.SIGTERM)
        updated = agent_run_manager.get(run.id)
        assert updated is not None
        assert updated.status == "error"
