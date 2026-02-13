"""Tmux pane death monitor.

Polls ``tmux -L gobby list-sessions`` to detect when agent tmux sessions
disappear (process exit, crash, user kill-pane) and synthesizes
``session_end`` events so the full teardown flow runs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.agents.tmux.config import TmuxConfig
from gobby.agents.tmux.session_manager import TmuxSessionManager
from gobby.hooks.events import HookEvent, HookEventType, SessionSource

if TYPE_CHECKING:
    from gobby.storage.session_models import Session
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)

# How long (seconds) a session_id stays in the recently-ended set
_RECENTLY_ENDED_TTL = 60.0


class TmuxPaneMonitor:
    """Background task that detects dead tmux panes and fires session_end.

    Args:
        session_end_callback: Called with a synthesized :class:`HookEvent`
            when a tmux session vanishes.  Typically
            ``EventHandlers.handle_session_end``.
        config: Tmux configuration (socket name, binary path, etc.).
        poll_interval: Seconds between polls (default 5).
    """

    def __init__(
        self,
        session_end_callback: Callable[[HookEvent], Any],
        config: TmuxConfig | None = None,
        poll_interval: float = 5.0,
        session_storage: LocalSessionManager | None = None,
    ) -> None:
        self._callback = session_end_callback
        self._config = config or TmuxConfig()
        self._poll_interval = poll_interval
        self._session_storage = session_storage
        self._tmux_mgr = TmuxSessionManager(self._config)
        self._task: asyncio.Task[None] | None = None
        # session_id -> timestamp when it was marked ended
        self._recently_ended: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background polling task."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._poll_loop(), name="tmux-pane-monitor")
        logger.info("TmuxPaneMonitor started (interval=%.1fs)", self._poll_interval)

    async def stop(self) -> None:
        """Cancel the background polling task."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("TmuxPaneMonitor stopped")

    def mark_recently_ended(self, session_id: str) -> None:
        """Record that *session_id* just had a normal session_end.

        This prevents the monitor from firing a duplicate event when it
        next polls and notices the tmux session is gone.
        """
        self._recently_ended[session_id] = time.monotonic()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Infinite loop: sleep, check panes, repeat."""
        while True:
            try:
                await asyncio.sleep(self._poll_interval)
                await self._check_panes()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("TmuxPaneMonitor poll error (continuing)")

    async def _check_panes(self) -> None:
        """Core detection: cross-reference live tmux sessions with registry."""
        from gobby.agents.registry import get_running_agent_registry

        # 1. Prune expired entries from recently-ended set
        now = time.monotonic()
        expired = [
            sid for sid, ts in self._recently_ended.items() if now - ts > _RECENTLY_ENDED_TTL
        ]
        for sid in expired:
            del self._recently_ended[sid]

        # 2. Get live tmux session names
        try:
            live_sessions = await self._tmux_mgr.list_sessions()
        except Exception:
            logger.warning("TmuxPaneMonitor: failed to list tmux sessions", exc_info=True)
            return
        live_names = {s.name for s in live_sessions}

        # 3. Get all agents with a tmux_session_name
        registry = get_running_agent_registry()
        agents = registry.list_all()
        tmux_agents = [a for a in agents if a.tmux_session_name]

        if not tmux_agents:
            return

        # 4. Fire session_end for agents whose tmux session is gone
        for agent in tmux_agents:
            if agent.tmux_session_name in live_names:
                continue
            if agent.session_id in self._recently_ended:
                continue

            logger.info(
                "Detected dead tmux pane for agent session=%s (tmux=%s)",
                agent.session_id,
                agent.tmux_session_name,
            )

            # Look up the session to get external_id and source
            session = self._lookup_session(agent.session_id)
            if session is None:
                logger.warning(
                    "Cannot synthesize session_end: session %s not found in DB",
                    agent.session_id,
                )
                self._recently_ended[agent.session_id] = now
                continue

            event = HookEvent(
                event_type=HookEventType.SESSION_END,
                session_id=session.external_id,
                source=SessionSource(session.source) if session.source else SessionSource.CLAUDE,
                timestamp=datetime.now(UTC),
                data={"cwd": None},
                metadata={
                    "_platform_session_id": session.id,
                    "_tmux_pane_death": True,
                },
            )

            try:
                self._callback(event)
            except Exception:
                logger.exception("TmuxPaneMonitor: callback error for session %s", agent.session_id)

            self._recently_ended[agent.session_id] = now

    def _lookup_session(self, session_id: str) -> Session | None:
        """Look up a session from the database."""
        if not self._session_storage:
            logger.debug("No session storage configured, cannot look up %s", session_id)
            return None
        try:
            return self._session_storage.get(session_id)
        except Exception:
            logger.debug("Failed to look up session %s", session_id, exc_info=True)
            return None
