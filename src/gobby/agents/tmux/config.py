"""Re-export TmuxConfig from canonical location to avoid circular imports.

The canonical definition lives in ``gobby.config.tmux`` (alongside other
config modules like ``servers.py``, ``sessions.py``). This shim lets
sibling modules import ``from gobby.agents.tmux.config import TmuxConfig``
without knowing the canonical location.
"""

from gobby.config.tmux import TmuxConfig

__all__ = ["TmuxConfig"]
