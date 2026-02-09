"""Promoted TmuxSpawner that delegates to TmuxSessionManager.

Replaces the old ``cross_platform.TmuxSpawner`` with a version that:

- Uses the isolated ``-L gobby`` socket via :class:`TmuxSessionManager`.
- Returns the session name in :attr:`SpawnResult.tmux_session_name` so
  callers can wire up output streaming and input forwarding.
- Remains a :class:`TerminalSpawnerBase` subclass for backward
  compatibility with :class:`TerminalSpawner`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from gobby.agents.spawners.base import (
    SpawnResult,
    TerminalSpawnerBase,
    TerminalType,
    make_spawn_env,
)
from gobby.agents.tmux.config import TmuxConfig
from gobby.agents.tmux.session_manager import TmuxSessionManager

logger = logging.getLogger(__name__)


class TmuxSpawner(TerminalSpawnerBase):
    """Spawner that creates tmux sessions on Gobby's isolated socket.

    Unlike the old spawner in ``cross_platform.py`` this version:

    * Uses ``-L gobby`` by default (configurable via :class:`TmuxConfig`).
    * Delegates to :class:`TmuxSessionManager` for session lifecycle.
    * Stores ``tmux_session_name`` on :class:`SpawnResult` so the caller
      can start output streaming and register the name on the agent.
    """

    def __init__(self, config: TmuxConfig | None = None) -> None:
        self._config = config or TmuxConfig()
        self._session_manager = TmuxSessionManager(self._config)

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.TMUX

    @property
    def session_manager(self) -> TmuxSessionManager:
        return self._session_manager

    def is_available(self) -> bool:
        if not self._config.enabled:
            return False
        return self._session_manager.is_available()

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        """Spawn a command inside a new tmux session (sync wrapper).

        The heavy lifting is async; we bridge to the running event loop
        or create a temporary one for sync callers (e.g.
        ``TerminalSpawner.spawn``).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an async context — schedule on the loop.
            # TerminalSpawner.spawn is called synchronously from
            # spawn_executor which is itself awaited, so this path is
            # taken when used from the executor.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self._async_spawn(command, cwd, env, title),
                )
                return future.result(timeout=30)
        else:
            return asyncio.run(self._async_spawn(command, cwd, env, title))

    async def _async_spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        """Async implementation of spawn."""
        import shlex

        session_name = title or f"{self._config.session_prefix}-{int(time.time())}"
        # Sanitise (TmuxSessionManager also sanitises, but normalise here
        # so the name we return is consistent).
        session_name = session_name.replace(".", "-").replace(":", "-")

        shell_cmd = shlex.join(command) if len(command) > 1 else command[0]

        # Merge env with a clean spawn env
        clean_env = make_spawn_env(env)
        # Only pass the *extra* env vars that differ from os.environ
        extra_env = {k: v for k, v in clean_env.items() if k in (env or {})}

        try:
            info = await self._session_manager.create_session(
                name=session_name,
                command=shell_cmd,
                cwd=str(cwd),
                env=extra_env,
            )
        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn tmux session: {e}",
                error=str(e),
            )

        result = SpawnResult(
            success=True,
            message=(
                f"Spawned tmux session '{info.name}' "
                f"(attach: tmux -L {self._config.socket_name} attach -t {info.name})"
            ),
            pid=info.pane_pid,
            terminal_type=self.terminal_type.value,
        )
        # Attach tmux_session_name to the result for callers that need it
        result.tmux_session_name = info.name  # type: ignore[attr-defined]
        return result
