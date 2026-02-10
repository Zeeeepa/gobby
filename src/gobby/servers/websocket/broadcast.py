"""WebSocket broadcast methods.

BroadcastMixin provides all broadcast_* methods for WebSocketServer.
Extracted from server.py as part of the Strangler Fig decomposition.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class BroadcastMixin:
    """Mixin providing broadcast methods for WebSocketServer.

    Requires ``self.clients: dict[Any, dict[str, Any]]`` on the host class.
    """

    clients: dict[Any, dict[str, Any]]

    def _is_subscribed(self, websocket: Any, message: dict[str, Any]) -> bool:
        """Check if a client is subscribed to receive a message."""
        # Clients without subscriptions receive nothing
        subs = getattr(websocket, "subscriptions", None)
        if subs is None:
            return False

        # Global wildcard subscription
        if "*" in subs:
            return True

        msg_type = message.get("type")

        # High-volume event types require explicit subscription
        event_types = {
            "hook_event",
            "session_message",
            "agent_event",
            "worktree_event",
            "autonomous_event",
            "pipeline_event",
            "terminal_output",
            "tmux_session_event",
        }

        # Non-event messages pass through for any subscribed client
        if msg_type not in event_types:
            return True

        # Check for message type subscription
        if msg_type in subs:
            return True

        # Special casing for hook_event granularity (subscribe by event_type)
        if msg_type == "hook_event":
            event_type = message.get("event_type")
            if event_type and event_type in subs:
                return True

        return False

    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Broadcast message to all connected clients.

        Filters messages based on client subscriptions using _is_subscribed.

        Args:
            message: Dictionary to serialize and send
        """
        if not self.clients:
            return

        message_str = json.dumps(message)
        sent_count = 0
        failed_count = 0

        for websocket in list(self.clients.keys()):
            try:
                if not self._is_subscribed(websocket, message):
                    continue

                await websocket.send(message_str)
                sent_count += 1
            except ConnectionClosed:
                # Client disconnecting, will be cleaned up in handler
                failed_count += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for client: {e}")
                failed_count += 1

        if sent_count > 0 or failed_count > 0:
            logger.debug(
                f"Broadcast {message.get('type')}: {sent_count} sent, {failed_count} failed"
            )

    async def broadcast_session_update(self, event: str, **kwargs: Any) -> None:
        """Broadcast session update (as session_message for back-compat)."""
        # Note: Logic in original broadcast() handled 'session_message' types.
        # We'll stick to that type for consistency with original expected behavior
        # or convert to 'session_update' if that was intended.
        # The original broadcast_session_update sent type="session_update",
        # but the original broadcast() loop checked "session_message".
        # We will assume "session_update" is safe to basic-broadcast if not restricted,
        # OR we should treat it as restricted.
        # Adding "session_update" to restricted types in _is_subscribed would require clients to sub.
        # Original code didn't restrict "session_update" type, only "session_message".
        # We'll treat "session_update" as a system message (unrestricted) for now unless it's noisy.
        message = {
            "type": "session_update",
            "event": event,
            **kwargs,
        }
        await self.broadcast(message)

    async def broadcast_agent_event(
        self,
        event: str,
        run_id: str,
        parent_session_id: str,
        **kwargs: Any,
    ) -> None:
        """Broadcast agent event."""
        message = {
            "type": "agent_event",
            "event": event,
            "run_id": run_id,
            "parent_session_id": parent_session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        await self.broadcast(message)

    async def broadcast_worktree_event(
        self,
        event: str,
        worktree_id: str,
        **kwargs: Any,
    ) -> None:
        """Broadcast worktree event."""
        message = {
            "type": "worktree_event",
            "event": event,
            "worktree_id": worktree_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        await self.broadcast(message)

    async def broadcast_autonomous_event(
        self,
        event: str,
        session_id: str,
        **kwargs: Any,
    ) -> None:
        """Broadcast autonomous execution event."""
        message = {
            "type": "autonomous_event",
            "event": event,
            "session_id": session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        await self.broadcast(message)

    async def broadcast_pipeline_event(
        self,
        event: str,
        execution_id: str,
        **kwargs: Any,
    ) -> None:
        """Broadcast pipeline execution event."""
        message = {
            "type": "pipeline_event",
            "event": event,
            "execution_id": execution_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        await self.broadcast(message)

    async def broadcast_terminal_output(
        self,
        run_id: str,
        data: str,
    ) -> None:
        """Broadcast terminal output."""
        message = {
            "type": "terminal_output",
            "run_id": run_id,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self.broadcast(message)
