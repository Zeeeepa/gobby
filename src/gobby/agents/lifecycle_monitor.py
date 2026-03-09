"""Background monitor for agent lifecycle.

Detects when agent tmux sessions die without firing SESSION_END hooks
and marks their DB records accordingly. This prevents ghost agents from
appearing in the UI as 'active' indefinitely.

Runs as a periodic background task alongside the session lifecycle manager.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import TYPE_CHECKING

from gobby.agents.idle_detector import IdleDetector
from gobby.agents.prompt_detector import PromptDetector
from gobby.agents.registry import RunningAgent, RunningAgentRegistry
from gobby.agents.tmux.session_manager import TmuxSessionManager
from gobby.config.tmux import TmuxConfig
from gobby.storage.agents import LocalAgentRunManager

if TYPE_CHECKING:
    from gobby.events.completion_registry import CompletionEventRegistry
    from gobby.hooks.session_coordinator import SessionCoordinator
    from gobby.storage.clones import LocalCloneManager
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)


class AgentLifecycleMonitor:
    """Periodically checks if agent tmux sessions are still alive.

    When a tmux session dies without firing SESSION_END hooks, this
    monitor detects the orphan and:
    - Marks the agent_runs DB record as 'error'
    - Removes the agent from the in-memory registry
    - Releases any associated worktrees
    """

    def __init__(
        self,
        agent_registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        session_coordinator: SessionCoordinator | None = None,
        clone_storage: LocalCloneManager | None = None,
        check_interval_seconds: float = 30.0,
        completion_registry: CompletionEventRegistry | None = None,
        task_manager: LocalTaskManager | None = None,
        tmux_config: TmuxConfig | None = None,
    ) -> None:
        self._registry = agent_registry
        self._agent_run_manager = agent_run_manager
        self._session_coordinator = session_coordinator
        self._clone_storage = clone_storage
        self._check_interval = check_interval_seconds
        self._completion_registry = completion_registry
        self._task_manager = task_manager
        self._tmux_config = tmux_config or TmuxConfig()
        self._tmux = TmuxSessionManager(config=self._tmux_config)
        self._idle_detector = IdleDetector()
        self._prompt_detector = PromptDetector()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def set_session_coordinator(self, coordinator: SessionCoordinator) -> None:
        """Inject session coordinator after construction (avoids circular init ordering)."""
        self._session_coordinator = coordinator

    async def _recover_task_from_failed_agent(self, run_id: str) -> None:
        """Reset a failed agent's task back to 'open' so the orchestrator can re-dispatch it."""
        if not self._task_manager:
            return
        try:
            db_run = await asyncio.to_thread(self._agent_run_manager.get, run_id)
            if not db_run or not db_run.task_id:
                return
            task = await asyncio.to_thread(self._task_manager.get_task, db_run.task_id)
            if task and task.status == "in_progress":
                await asyncio.to_thread(
                    self._task_manager.update_task, db_run.task_id, status="open", assignee=None
                )
                task_ref = f"#{task.seq_num}" if task.seq_num else db_run.task_id[:8]
                logger.info("Recovered task %s to open after agent %s failed", task_ref, run_id)
        except Exception as e:
            logger.warning("Failed to recover task for agent %s: %s", run_id, e)

    async def start(self) -> None:
        """Start the monitoring loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._check_loop(),
            name="agent-lifecycle-monitor",
        )
        logger.info(f"AgentLifecycleMonitor started (interval={self._check_interval}s)")

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("AgentLifecycleMonitor stopped")

    async def _check_loop(self) -> None:
        """Periodic check loop."""
        # Brief initial delay to let agents finish spawning on startup
        await asyncio.sleep(5.0)

        while self._running:
            try:
                await self.check_trust_prompts()  # Fast unblock before other checks
                await self.check_dead_agents()
                await self.check_expired_agents()
                await self.check_idle_agents()
            except Exception as e:
                logger.error(f"Agent lifecycle check error: {e}")

            try:
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break

    async def check_trust_prompts(self) -> int:
        """Check for folder trust prompts and auto-dismiss them.

        Sends key "2" (Trust parent Folder) + Enter to dismiss the prompt.
        Only fires once per agent to avoid repeated key-sends.

        Returns:
            Number of trust prompts dismissed.
        """
        agents = self._registry.list_all()
        tmux_agents = [a for a in agents if a.mode == "terminal" and a.tmux_session_name]

        handled = 0
        for agent in tmux_agents:
            if self._prompt_detector.was_dismissed(agent.run_id):
                continue

            tmux_name = agent.tmux_session_name
            assert tmux_name is not None  # guaranteed by filter above

            try:
                pane_output = await self._tmux.capture_pane(tmux_name, lines=15)
                if pane_output and self._prompt_detector.detect_trust_prompt(pane_output):
                    sent = await self._tmux.send_keys(tmux_name, PromptDetector.TRUST_DISMISS_KEYS)
                    if sent:
                        self._prompt_detector.mark_dismissed(agent.run_id)
                        logger.info(
                            "Auto-dismissed trust prompt for agent %s (trust parent folder)",
                            agent.run_id,
                        )
                        handled += 1
            except Exception as e:
                logger.warning("Error checking trust prompt for agent %s: %s", agent.run_id, e)

        return handled

    async def check_dead_agents(self) -> int:
        """Check for dead agents (tmux and autonomous) and clean up.

        Returns:
            Number of dead agents cleaned up.
        """
        agents = self._registry.list_all()

        # Check terminal-mode agents that have a tmux session name
        tmux_agents = [a for a in agents if a.mode == "terminal" and a.tmux_session_name]

        cleaned = 0
        for agent in tmux_agents:
            try:
                tmux_name = agent.tmux_session_name
                assert tmux_name is not None  # guaranteed by filter above
                alive = await self._tmux.has_session(tmux_name)
                if alive:
                    continue

                logger.info(
                    f"Detected dead tmux session '{agent.tmux_session_name}' "
                    f"for agent {agent.run_id}"
                )

                # Kill orphaned process before cleanup
                if agent.pid:
                    try:
                        os.kill(agent.pid, signal.SIGTERM)
                        logger.info(
                            f"Sent SIGTERM to orphaned agent process {agent.pid} "
                            f"(run {agent.run_id})"
                        )
                    except ProcessLookupError:
                        pass  # Already dead
                    except Exception as e:
                        logger.warning(f"Failed to kill orphaned process {agent.pid}: {e}")

                # Mark DB record as error if still in active status
                # These are sync DB calls — run off the event loop to avoid blocking
                db_run = await asyncio.to_thread(self._agent_run_manager.get, agent.run_id)
                if db_run and db_run.status in ("pending", "running"):
                    await asyncio.to_thread(
                        self._agent_run_manager.fail,
                        agent.run_id,
                        error="tmux session died unexpectedly",
                    )
                    logger.info(f"Marked agent run {agent.run_id} as failed (dead tmux session)")

                # Recover the task so orchestrator can re-dispatch
                await self._recover_task_from_failed_agent(agent.run_id)

                # Fire completion event so orchestrator continuations trigger
                if self._completion_registry:
                    try:
                        await self._completion_registry.notify(
                            agent.run_id,
                            result={"status": "error", "error": "tmux session died unexpectedly"},
                            message=f"Agent {agent.run_id} failed (tmux session died)",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to notify completion for {agent.run_id}: {e}")

                # Remove from in-memory registry
                self._registry.remove(agent.run_id, status="failed")

                # Clean up detector state
                self._prompt_detector.clear(agent.run_id)

                # Release worktrees
                if self._session_coordinator:
                    try:
                        self._session_coordinator.release_session_worktrees(agent.session_id)
                    except Exception as e:
                        logger.warning(f"Failed to release worktrees for agent {agent.run_id}: {e}")

                # Release clones
                if self._clone_storage and agent.clone_id:
                    try:
                        await asyncio.to_thread(self._clone_storage.release, agent.clone_id)
                    except Exception as e:
                        logger.warning(f"Failed to release clone for agent {agent.run_id}: {e}")

                cleaned += 1

            except Exception as e:
                logger.warning(f"Error checking agent {agent.run_id}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} dead tmux agent(s)")

        # Check autonomous/in_process agents with asyncio.Tasks
        task_agents = [
            a for a in agents if a.task is not None and a.mode in ("autonomous", "in_process")
        ]
        for agent in task_agents:
            task: asyncio.Task[object] = agent.task  # type: ignore[assignment]
            if not task.done():
                continue

            try:
                exc = task.exception()
                if exc:
                    error_msg = f"Autonomous agent failed: {exc}"
                    logger.info(f"Detected failed autonomous task for agent {agent.run_id}: {exc}")
                else:
                    error_msg = None
                    logger.info(f"Detected completed autonomous task for agent {agent.run_id}")
            except asyncio.CancelledError:
                error_msg = "Autonomous agent was cancelled"
                logger.info(f"Detected cancelled autonomous task for agent {agent.run_id}")

            try:
                # Update DB record
                db_run = await asyncio.to_thread(self._agent_run_manager.get, agent.run_id)
                if db_run and db_run.status in ("pending", "running"):
                    if error_msg:
                        await asyncio.to_thread(
                            self._agent_run_manager.fail,
                            agent.run_id,
                            error=error_msg,
                        )
                    else:
                        await asyncio.to_thread(
                            self._agent_run_manager.complete,
                            agent.run_id,
                            result="Completed (detected by lifecycle monitor)",
                        )

                # Recover the task if the agent failed
                if error_msg:
                    await self._recover_task_from_failed_agent(agent.run_id)

                # Fire completion event so orchestrator continuations trigger
                if self._completion_registry:
                    try:
                        result_data = (
                            {"status": "error", "error": error_msg}
                            if error_msg
                            else {"status": "completed"}
                        )
                        await self._completion_registry.notify(
                            agent.run_id,
                            result=result_data,
                            message=f"Agent {agent.run_id} {'failed' if error_msg else 'completed'}",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to notify completion for {agent.run_id}: {e}")

                # Remove from in-memory registry
                status = "failed" if error_msg else "completed"
                self._registry.remove(agent.run_id, status=status)

                # Release worktrees
                if self._session_coordinator:
                    try:
                        self._session_coordinator.release_session_worktrees(agent.session_id)
                    except Exception as e:
                        logger.warning(f"Failed to release worktrees for agent {agent.run_id}: {e}")

                # Release clones
                if self._clone_storage and agent.clone_id:
                    try:
                        await asyncio.to_thread(self._clone_storage.release, agent.clone_id)
                    except Exception as e:
                        logger.warning(f"Failed to release clone for agent {agent.run_id}: {e}")

                cleaned += 1

            except Exception as e:
                logger.warning(f"Error cleaning up autonomous agent {agent.run_id}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} dead agent(s) total")

        return cleaned

    async def check_expired_agents(self) -> int:
        """Check for agents that have exceeded their timeout and kill them.

        Returns:
            Number of expired agents cleaned up.
        """
        import datetime

        agents = self._registry.list_all()
        now = datetime.datetime.now(datetime.UTC)
        cleaned = 0

        for agent in agents:
            if not agent.timeout_seconds:
                continue

            age = (now - agent.started_at).total_seconds()
            if age <= agent.timeout_seconds:
                continue

            try:
                logger.info(
                    f"Agent {agent.run_id} exceeded timeout ({age:.1f}s > {agent.timeout_seconds}s). Killing..."
                )

                # Kill process via registry
                await self._registry.kill(
                    agent.run_id,
                    signal_name="TERM",
                    timeout=5.0,
                    close_terminal=True,
                )

                # Mark DB record as timeout
                await asyncio.to_thread(
                    self._agent_run_manager.fail,
                    agent.run_id,
                    error=f"Agent exceeded {agent.timeout_seconds}s timeout",
                )

                # Remove from in-memory registry if kill() didn't
                if self._registry.get(agent.run_id):
                    self._registry.remove(agent.run_id, status="timeout")

                # Release worktrees
                if self._session_coordinator:
                    try:
                        self._session_coordinator.release_session_worktrees(agent.session_id)
                    except Exception as e:
                        logger.warning(
                            f"Failed to release worktrees for expired agent {agent.run_id}: {e}"
                        )

                # Release clones
                if self._clone_storage and agent.clone_id:
                    try:
                        await asyncio.to_thread(self._clone_storage.release, agent.clone_id)
                    except Exception as e:
                        logger.warning(
                            f"Failed to release clone for expired agent {agent.run_id}: {e}"
                        )

                cleaned += 1

            except Exception as e:
                logger.warning(f"Error checking expiration for agent {agent.run_id}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired agent(s)")

        return cleaned

    async def check_idle_agents(self) -> int:
        """Check for idle agents and reprompt or fail them.

        Returns:
            Number of agents reprompted or failed.
        """
        if not self._tmux_config.idle_check_enabled:
            return 0

        agents = self._registry.list_all()
        tmux_agents = [a for a in agents if a.mode == "terminal" and a.tmux_session_name]

        handled = 0
        for agent in tmux_agents:
            try:
                handled += await self._handle_idle_check(agent)
            except Exception as e:
                logger.warning(f"Error checking idle state for agent {agent.run_id}: {e}")

        return handled

    async def _handle_idle_check(self, agent: RunningAgent) -> int:
        """Handle idle check for a single agent. Returns 1 if action taken, 0 otherwise."""
        tmux_name = agent.tmux_session_name
        assert tmux_name is not None

        # Capture last 15 lines from pane (need enough to see past status bar)
        pane_output = await self._tmux.capture_pane(tmux_name, lines=15)
        if pane_output is None:
            return 0

        status = self._idle_detector.detect(pane_output)

        if status == "active":
            self._idle_detector.reset_idle(agent.run_id)
            return 0

        if status == "context_full":
            logger.info(f"Agent {agent.run_id} hit context window limit — failing")
            await self._fail_idle_agent(agent, reason="context window exhausted")
            return 1

        # status == "idle"
        if self._idle_detector.should_fail(agent.run_id, self._tmux_config.max_reprompt_attempts):
            logger.info(
                f"Agent {agent.run_id} still idle after "
                f"{self._tmux_config.max_reprompt_attempts} reprompts — failing"
            )
            await self._fail_idle_agent(agent, reason="idle after max reprompt attempts")
            return 1

        if self._idle_detector.should_reprompt(
            agent.run_id,
            self._tmux_config.idle_timeout_seconds,
            self._tmux_config.max_reprompt_attempts,
        ):
            logger.info(f"Reprompting idle agent {agent.run_id}")
            sent = await self._tmux.send_keys(tmux_name, IdleDetector.REPROMPT_MESSAGE + "\n")
            if sent:
                self._idle_detector.record_reprompt(agent.run_id)
            return 1

        return 0

    async def _fail_idle_agent(self, agent: RunningAgent, reason: str) -> None:
        """Fail an agent that is irrecoverably idle."""
        # Mark DB record as error
        db_run = await asyncio.to_thread(self._agent_run_manager.get, agent.run_id)
        if db_run and db_run.status in ("pending", "running"):
            await asyncio.to_thread(
                self._agent_run_manager.fail,
                agent.run_id,
                error=f"Agent idle: {reason}",
            )

        # Recover task to open
        await self._recover_task_from_failed_agent(agent.run_id)

        # Fire completion event
        if self._completion_registry:
            try:
                await self._completion_registry.notify(
                    agent.run_id,
                    result={"status": "error", "error": f"Agent idle: {reason}"},
                    message=f"Agent {agent.run_id} failed ({reason})",
                )
            except Exception as e:
                logger.warning(f"Failed to notify completion for {agent.run_id}: {e}")

        # Kill tmux session
        tmux_name = agent.tmux_session_name
        if tmux_name:
            await self._tmux.kill_session(tmux_name)

        # Clean up detector state
        self._idle_detector.clear_state(agent.run_id)
        self._prompt_detector.clear(agent.run_id)

        # Remove from registry
        self._registry.remove(agent.run_id, status="failed")

        # Release worktrees
        if self._session_coordinator:
            try:
                self._session_coordinator.release_session_worktrees(agent.session_id)
            except Exception as e:
                logger.warning(f"Failed to release worktrees for idle agent {agent.run_id}: {e}")

        # Release clones
        if self._clone_storage and agent.clone_id:
            try:
                await asyncio.to_thread(self._clone_storage.release, agent.clone_id)
            except Exception as e:
                logger.warning(f"Failed to release clone for idle agent {agent.run_id}: {e}")

    async def cleanup_stale_pending_runs(self) -> int:
        """Clean up agent runs stuck in pending status after daemon restart.

        Returns:
            Number of stale pending runs cleaned up.
        """
        return await asyncio.to_thread(self._agent_run_manager.cleanup_stale_pending_runs)

    async def recover_or_cleanup_agents(self) -> tuple[int, int]:
        """Recover alive agents or clean up dead ones after daemon restart.

        Checks agent_runs still in 'running' or 'pending' (with PID) status.
        If the process and tmux session are still alive, re-registers the agent
        in the in-memory registry. Otherwise, marks the run as failed and
        recovers the task.

        Returns:
            Tuple of (recovered_count, cleaned_count).
        """
        running_runs = await asyncio.to_thread(self._agent_run_manager.list_running)
        pending_runs = await asyncio.to_thread(self._agent_run_manager.list_pending_with_pid)

        recovered = 0
        cleaned = 0

        for run in running_runs + pending_runs:
            # Skip runs already tracked in registry (shouldn't happen on restart, but safe)
            if self._registry.get(run.id):
                continue

            # Check 1: Is the process still alive?
            pid_alive = False
            if run.pid:
                try:
                    os.kill(run.pid, 0)
                    pid_alive = True
                except (ProcessLookupError, PermissionError):
                    pass

            # Check 2: Does the tmux session still exist?
            tmux_alive = False
            if run.tmux_session_name:
                tmux_alive = await self._tmux.has_session(run.tmux_session_name)

            if pid_alive and tmux_alive:
                # Agent is alive — re-register in memory
                self._registry.add(
                    RunningAgent(
                        run_id=run.id,
                        session_id=run.child_session_id or run.parent_session_id,
                        parent_session_id=run.parent_session_id,
                        mode=run.mode or "terminal",
                        pid=run.pid,
                        tmux_session_name=run.tmux_session_name,
                        provider=run.provider,
                        worktree_id=run.worktree_id,
                        clone_id=run.clone_id,
                    )
                )
                logger.info(
                    "Recovered agent %s (pid=%s, tmux=%s)",
                    run.id,
                    run.pid,
                    run.tmux_session_name,
                )
                recovered += 1
            elif pid_alive and not tmux_alive:
                # Process alive but tmux dead — kill the orphan, mark failed
                try:
                    if run.pid:
                        os.kill(run.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                await asyncio.to_thread(
                    self._agent_run_manager.fail,
                    run.id,
                    error="tmux session lost after daemon restart",
                )
                await self._recover_task_from_failed_agent(run.id)
                await self._fire_orphan_completion(run.id)
                cleaned += 1
            else:
                # Both dead — mark failed
                await asyncio.to_thread(
                    self._agent_run_manager.fail,
                    run.id,
                    error="Orphaned after daemon restart",
                )
                await self._recover_task_from_failed_agent(run.id)
                await self._fire_orphan_completion(run.id)
                logger.info("Cleaned up orphaned agent run %s", run.id)
                cleaned += 1

        return recovered, cleaned

    async def _fire_orphan_completion(self, run_id: str) -> None:
        """Fire a completion event for an orphaned agent run."""
        if not self._completion_registry:
            return
        try:
            if not self._completion_registry.is_registered(run_id):
                self._completion_registry.register(run_id, subscribers=[])
            await self._completion_registry.notify(
                run_id,
                result={"status": "error", "error": "Orphaned (daemon restarted)"},
                message=f"Agent {run_id} orphaned after daemon restart",
            )
        except Exception:
            logger.exception("Failed to fire orphan completion for run %s", run_id)
