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

    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Broadcast message to all connected clients.

        Filters messages based on client subscriptions:
        1. If message type is NOT 'hook_event', always send (system messages)
        2. If message type IS 'hook_event':
           - If client has NO subscriptions, send ALL events (default behavior)
           - If client HAS subscriptions, only send if event_type in subscriptions

        Args:
            message: Dictionary to serialize and send
        """
        if not self.clients:
            return  # No clients connected, silently skip

        message_str = json.dumps(message)
        sent_count = 0
        failed_count = 0

        # Pre-calculate filtering criteria
        is_hook_event = message.get("type") == "hook_event"
        event_type = message.get("event_type")

        for websocket in list(self.clients.keys()):
            try:
                # Filter by subscription: clients must subscribe to receive events
                subs = getattr(websocket, "subscriptions", None)
                if subs is None:
                    # No subscriptions = receive nothing
                    continue

                if is_hook_event:
                    if event_type not in subs and "*" not in subs:
                        continue
                elif message.get("type") == "session_message":
                    if "session_message" not in subs and "*" not in subs:
                        continue

                await websocket.send(message_str)
                sent_count += 1
            except ConnectionClosed:
                # Client disconnecting, will be cleaned up in handler
                failed_count += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for client: {e}")
                failed_count += 1

        logger.debug(f"Broadcast complete: {sent_count} sent, {failed_count} failed")

    async def broadcast_session_update(self, event: str, **kwargs: Any) -> None:
        """
        Broadcast session update to all clients.

        Convenience method for sending session_update messages.

        Args:
            event: Event type (e.g., "token_refreshed", "logout")
            **kwargs: Additional event data
        """
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
        """
        Broadcast agent event to all clients.

        Used for agent lifecycle events like started, completed, cancelled.

        Args:
            event: Event type (agent_started, agent_completed, agent_failed, agent_cancelled)
            run_id: Agent run ID
            parent_session_id: Parent session that spawned the agent
            **kwargs: Additional event data (provider, status, etc.)
        """
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
        """
        Broadcast worktree event to all clients.

        Used for worktree lifecycle events like created, claimed, released, merged.

        Args:
            event: Event type (worktree_created, worktree_claimed, worktree_released, worktree_merged)
            worktree_id: Worktree ID
            **kwargs: Additional event data (branch_name, task_id, session_id, etc.)
        """
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
        """
        Broadcast autonomous execution event to all clients.

        Used for autonomous loop lifecycle and progress events:
        - task_started: A task was selected for work
        - task_completed: A task was completed
        - validation_failed: Task validation failed
        - stuck_detected: Loop detected stuck condition
        - stop_requested: External stop signal received
        - progress_recorded: Progress event recorded
        - loop_started: Autonomous loop started
        - loop_stopped: Autonomous loop stopped

        Args:
            event: Event type
            session_id: Session ID of the autonomous loop
            **kwargs: Additional event data (task_id, reason, details, etc.)
        """
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
        """
        Broadcast pipeline execution event to subscribed clients.

        Used for real-time pipeline execution updates:
        - pipeline_started: Execution began
        - pipeline_completed: Execution finished successfully
        - pipeline_failed: Execution failed with error
        - step_started: A step began executing
        - step_completed: A step finished successfully
        - step_failed: A step failed with error
        - step_output: Streaming output from a step
        - approval_required: Step is waiting for approval

        Args:
            event: Event type
            execution_id: Pipeline execution ID
            **kwargs: Additional event data (step_id, output, error, etc.)
        """
        if not self.clients:
            return  # No clients connected

        message = {
            "type": "pipeline_event",
            "event": event,
            "execution_id": execution_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        message_str = json.dumps(message)

        for websocket in list(self.clients.keys()):
            try:
                # Only send to clients subscribed to pipeline_event or *
                subs = getattr(websocket, "subscriptions", None)
                if subs is not None:
                    if "pipeline_event" not in subs and "*" not in subs:
                        continue

                await websocket.send(message_str)
            except ConnectionClosed:
                pass
            except Exception as e:
                logger.warning(f"Pipeline event broadcast failed: {e}")

    async def broadcast_terminal_output(
        self,
        run_id: str,
        data: str,
    ) -> None:
        """
        Broadcast terminal output to subscribed clients.

        Used for streaming PTY output from embedded agents to web terminals.

        Args:
            run_id: Agent run ID
            data: Raw terminal output data
        """
        if not self.clients:
            return  # No clients connected

        message = {
            "type": "terminal_output",
            "run_id": run_id,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        message_str = json.dumps(message)

        for websocket in list(self.clients.keys()):
            try:
                # Only send to clients subscribed to terminal_output or *
                subs = getattr(websocket, "subscriptions", None)
                if subs is not None:
                    if "terminal_output" not in subs and "*" not in subs:
                        continue

                await websocket.send(message_str)
            except ConnectionClosed:
                pass
            except Exception as e:
                logger.warning(f"Terminal broadcast failed: {e}")
