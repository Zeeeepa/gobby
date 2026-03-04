"""Wake dispatcher for notifying sessions when async operations complete.

Routes wake messages based on session type:
- Terminal agents (agent_depth > 0, terminal_context): tmux send-keys
- Interactive sessions (agent_depth 0): InterSessionMessage
- Fallback: ISM if tmux/SDK fails
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# tmux_sender signature: (tmux_session_name: str, message: str) -> None
TmuxSender = Callable[[str, str], Coroutine[Any, Any, None]]


class WakeDispatcher:
    """Dispatches wake messages to sessions based on their type.

    Constructor args:
        session_manager: For looking up session metadata (agent_depth, terminal_context)
        ism_manager: For creating InterSessionMessages (durable fallback)
        tmux_sender: Optional async callable to send keys to a tmux session
    """

    def __init__(
        self,
        session_manager: Any,
        ism_manager: Any,
        tmux_sender: TmuxSender | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._ism_manager = ism_manager
        self._tmux_sender = tmux_sender

    async def wake(
        self,
        session_id: str,
        message: str,
        result: dict[str, Any],
    ) -> None:
        """Wake a session with a completion notification.

        Args:
            session_id: Target session to wake
            message: Human-readable notification message
            result: Structured result data
        """
        session = self._session_manager.get(session_id)
        if session is None:
            logger.warning("Cannot wake session %s: not found", session_id)
            return

        agent_depth = getattr(session, "agent_depth", 0) or 0

        # Interactive session → always ISM
        if agent_depth == 0:
            self._send_ism(session_id, message)
            return

        # Terminal agent → try tmux, fall back to ISM
        terminal_context = getattr(session, "terminal_context", None)
        if terminal_context and self._tmux_sender:
            tmux_session_name = self._parse_tmux_session(terminal_context)
            if tmux_session_name:
                try:
                    await self._tmux_sender(tmux_session_name, message)
                    return
                except Exception:
                    logger.warning(
                        "tmux wake failed for session %s (tmux=%s), falling back to ISM",
                        session_id,
                        tmux_session_name,
                        exc_info=True,
                    )

        # Fallback: ISM
        self._send_ism(session_id, message)

    def _send_ism(self, session_id: str, message: str) -> None:
        """Send an InterSessionMessage as durable notification."""
        try:
            self._ism_manager.create_message(
                from_session=session_id,  # self-notification (system → session)
                to_session=session_id,
                content=message,
                message_type="completion_notification",
                priority="high",
            )
        except Exception:
            logger.error(
                "Failed to send ISM to session %s",
                session_id,
                exc_info=True,
            )

    @staticmethod
    def _parse_tmux_session(terminal_context: str) -> str | None:
        """Extract tmux session name from terminal_context JSON."""
        try:
            ctx = json.loads(terminal_context)
            return ctx.get("tmux_session")
        except (json.JSONDecodeError, TypeError):
            return None
