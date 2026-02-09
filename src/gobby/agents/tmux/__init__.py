"""First-class tmux agent spawning module.

Provides session management, output streaming, and a promoted spawner
for tmux-based agent execution with web UI visibility.

Public API::

    from gobby.agents.tmux import (
        get_tmux_session_manager,
        get_tmux_output_reader,
        TmuxSpawner,
        TmuxConfig,
    )
"""

from __future__ import annotations

import threading

from gobby.agents.tmux.config import TmuxConfig
from gobby.agents.tmux.errors import TmuxNotFoundError, TmuxSessionError
from gobby.agents.tmux.output_reader import TmuxOutputReader
from gobby.agents.tmux.session_manager import TmuxSessionManager
from gobby.agents.tmux.spawner import TmuxSpawner

__all__ = [
    "TmuxConfig",
    "TmuxNotFoundError",
    "TmuxOutputReader",
    "TmuxSessionError",
    "TmuxSessionManager",
    "TmuxSpawner",
    "get_tmux_output_reader",
    "get_tmux_session_manager",
]

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
_session_manager: TmuxSessionManager | None = None
_output_reader: TmuxOutputReader | None = None
_lock = threading.Lock()


def get_tmux_session_manager(config: TmuxConfig | None = None) -> TmuxSessionManager:
    """Return the global :class:`TmuxSessionManager` singleton."""
    global _session_manager
    if _session_manager is None:
        with _lock:
            if _session_manager is None:
                _session_manager = TmuxSessionManager(config)
    return _session_manager


def get_tmux_output_reader(config: TmuxConfig | None = None) -> TmuxOutputReader:
    """Return the global :class:`TmuxOutputReader` singleton."""
    global _output_reader
    if _output_reader is None:
        with _lock:
            if _output_reader is None:
                _output_reader = TmuxOutputReader(config)
    return _output_reader
