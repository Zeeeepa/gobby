"""WebSocket message handlers.

HandlerMixin provides individual message type handlers for WebSocketServer.
Extracted from server.py as part of the Strangler Fig decomposition.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from gobby.agents.registry import get_running_agent_registry
from gobby.mcp_proxy.manager import MCPClientManager

logger = logging.getLogger(__name__)


class HandlerMixin:
    """Mixin providing message handler methods for WebSocketServer.

    Requires on the host class:
    - ``self.mcp_manager: MCPClientManager``
    - ``self.stop_registry: Any``
    - ``self.broadcast_autonomous_event(...)`` (from BroadcastMixin)
    """

    mcp_manager: MCPClientManager
    stop_registry: Any

    async def broadcast_autonomous_event(
        self, event: str, session_id: str, **kwargs: Any
    ) -> None: ...

    async def _send_error(
        self,
        websocket: Any,
        message: str,
        request_id: str | None = None,
        code: str = "ERROR",
    ) -> None:
        """
        Send error message to client.

        Args:
            websocket: Client WebSocket connection
            message: Error message
            request_id: Optional request ID for correlation
            code: Error code (default: "ERROR")
        """
        error_msg: dict[str, Any] = {
            "type": "error",
            "code": code,
            "message": message,
        }

        if request_id:
            error_msg["request_id"] = request_id

        await websocket.send(json.dumps(error_msg))

    async def _handle_tool_call(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle tool_call message and route to MCP server.

        Fires BEFORE_TOOL / AFTER_TOOL hook events so that rules can block
        or observe direct websocket tool calls (parity with CLI adapter).

        Message format:
        {
            "type": "tool_call",
            "request_id": "uuid",
            "mcp": "memory",
            "tool": "add_messages",
            "args": {...}
        }

        Response format:
        {
            "type": "tool_result",
            "request_id": "uuid",
            "result": {...}
        }

        Args:
            websocket: Client WebSocket connection
            data: Parsed tool call message
        """
        request_id = data.get("request_id")
        mcp_name = data.get("mcp")
        tool_name = data.get("tool")
        args = data.get("args", {})

        if (
            not isinstance(request_id, str)
            or not isinstance(mcp_name, str)
            or not isinstance(tool_name, str)
        ):
            await self._send_error(
                websocket,
                "Missing or invalid required fields: request_id, mcp, tool (must be strings)",
                request_id=str(request_id) if request_id else None,
            )
            return

        # --- BEFORE_TOOL: evaluate rules before executing the call ---
        blocked = await self._evaluate_tool_hook_before(mcp_name, tool_name, args)
        if blocked:
            await self._send_error(
                websocket,
                blocked,
                request_id=request_id,
                code="BLOCKED",
            )
            return

        try:
            # Route to internal registries first, then external MCP
            internal_mgr = getattr(self, "internal_manager", None)
            if internal_mgr and internal_mgr.is_internal(mcp_name):
                registry = internal_mgr.get_registry(mcp_name)
                if registry:
                    try:
                        result = await registry.call(tool_name, args)
                    except ValueError:
                        result = await self.mcp_manager.call_tool(mcp_name, tool_name, args)
                else:
                    result = await self.mcp_manager.call_tool(mcp_name, tool_name, args)
            else:
                result = await self.mcp_manager.call_tool(mcp_name, tool_name, args)

            # Send result back to client
            await websocket.send(
                json.dumps(
                    {
                        "type": "tool_result",
                        "request_id": request_id,
                        "result": result,
                    }
                )
            )

            # --- AFTER_TOOL: best-effort, non-blocking ---
            self._fire_tool_hook_after(mcp_name, tool_name, args, result)

        except ValueError as e:
            # Unknown MCP server
            await self._send_error(websocket, str(e), request_id=request_id)

        except Exception as e:
            logger.exception(f"Tool call error: {mcp_name}.{tool_name}")
            await self._send_error(websocket, f"Tool call failed: {str(e)}", request_id=request_id)

    async def _evaluate_tool_hook_before(
        self,
        mcp_name: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> str | None:
        """Fire BEFORE_TOOL for a direct websocket tool call.

        Returns a block reason string if the call should be denied, or None
        to proceed.  Fails open on any evaluation error.
        """
        workflow_handler = getattr(self, "workflow_handler", None)
        if not workflow_handler:
            return None

        from datetime import UTC, datetime

        from gobby.hooks.events import HookEvent, HookEventType, SessionSource

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="",
            source=SessionSource.CLAUDE_SDK_WEB_CHAT,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": f"mcp__{mcp_name}__{tool_name}",
                "tool_input": args,
                "mcp_server": mcp_name,
                "mcp_tool": tool_name,
            },
        )

        try:
            from gobby.hooks.events import HookResponse

            response: HookResponse = await asyncio.to_thread(workflow_handler.evaluate, event)
            if response.decision in ("deny", "block"):
                return response.reason or "Blocked by rule"
        except Exception:
            logger.debug(
                "BEFORE_TOOL evaluation failed for %s.%s (fail-open)",
                mcp_name,
                tool_name,
                exc_info=True,
            )

        return None

    def _fire_tool_hook_after(
        self,
        mcp_name: str,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
    ) -> None:
        """Fire AFTER_TOOL for a direct websocket tool call (best-effort)."""
        workflow_handler = getattr(self, "workflow_handler", None)
        if not workflow_handler:
            return

        from datetime import UTC, datetime

        from gobby.hooks.events import HookEvent, HookEventType, SessionSource

        # Truncate tool output to avoid bloating event data
        result_str = str(result)
        if len(result_str) > 500:
            result_str = result_str[:500] + "..."

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="",
            source=SessionSource.CLAUDE_SDK_WEB_CHAT,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": f"mcp__{mcp_name}__{tool_name}",
                "tool_input": args,
                "mcp_server": mcp_name,
                "mcp_tool": tool_name,
                "tool_output": result_str,
            },
        )

        async def _eval() -> None:
            try:
                await asyncio.to_thread(workflow_handler.evaluate, event)
            except Exception:
                logger.debug(
                    "AFTER_TOOL evaluation failed for %s.%s", mcp_name, tool_name, exc_info=True
                )

        asyncio.create_task(_eval())

    async def _handle_ping(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle manual ping message for latency measurement.

        Sends pong response with latency value.

        Args:
            websocket: Client WebSocket connection
            data: Ping message (ignored)
        """
        await websocket.send(
            json.dumps(
                {
                    "type": "pong",
                    "latency": getattr(websocket, "latency", 0.0),
                }
            )
        )

    async def _handle_subscribe(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle subscribe message to register for specific events.

        Args:
            websocket: Client WebSocket connection
            data: Subscribe message with "events" list
        """
        events = data.get("events", [])
        if not isinstance(events, list):
            await self._send_error(websocket, "events must be a list of strings")
            return

        if not hasattr(websocket, "subscriptions") or websocket.subscriptions is None:
            websocket.subscriptions = set()

        websocket.subscriptions.update(events)
        logger.debug(f"Client {websocket.user_id} subscribed to: {events}")

        await websocket.send(
            json.dumps(
                {
                    "type": "subscribe_success",
                    "events": list(websocket.subscriptions),
                }
            )
        )

    async def _handle_unsubscribe(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle unsubscribe message to unregister from specific events.

        Args:
            websocket: Client WebSocket connection
            data: Unsubscribe message with "events" list
        """
        events = data.get("events", [])
        if not isinstance(events, list):
            await self._send_error(websocket, "events must be a list of strings")
            return

        current_subscriptions: set[str] = getattr(websocket, "subscriptions", set())

        # If events list is empty or contains "*", unsubscribe from all
        if not events or "*" in events:
            current_subscriptions.clear()
        else:
            for event in events:
                current_subscriptions.discard(event)

        logger.debug(f"Client {websocket.user_id} unsubscribed from: {events}")

        await websocket.send(
            json.dumps(
                {
                    "type": "unsubscribe_success",
                    "events": list(current_subscriptions),
                }
            )
        )

    async def _handle_stop_request(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle stop_request message to signal a session to stop.

        Message format:
        {
            "type": "stop_request",
            "session_id": "uuid",
            "reason": "optional reason string"
        }

        Response format:
        {
            "type": "stop_response",
            "session_id": "uuid",
            "success": true,
            "signal_id": "uuid"
        }

        Args:
            websocket: Client WebSocket connection
            data: Parsed stop request message
        """
        session_id = data.get("session_id")
        reason = data.get("reason", "WebSocket stop request")

        if not session_id:
            await self._send_error(websocket, "Missing required field: session_id")
            return

        if not self.stop_registry:
            await self._send_error(websocket, "Stop registry not available", code="UNAVAILABLE")
            return

        try:
            # Signal the stop
            signal = self.stop_registry.signal_stop(
                session_id=session_id,
                reason=reason,
                source="websocket",
            )

            # Send acknowledgment
            await websocket.send(
                json.dumps(
                    {
                        "type": "stop_response",
                        "session_id": session_id,
                        "success": True,
                        "signal_id": signal.session_id,
                        "signaled_at": signal.requested_at.isoformat(),
                    }
                )
            )

            # Broadcast the stop_requested event to all clients
            await self.broadcast_autonomous_event(
                event="stop_requested",
                session_id=session_id,
                reason=reason,
                source="websocket",
                signal_id=signal.session_id,
            )

            logger.info(f"Stop requested for session {session_id} via WebSocket")
        except Exception as e:
            logger.error(f"Error handling stop request: {e}")
            await self._send_error(websocket, f"Failed to signal stop: {str(e)}")

    async def _handle_terminal_input(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle terminal input for a running agent.

        Message format:
        {
            "type": "terminal_input",
            "run_id": "uuid",
            "data": "raw input string"
        }

        Args:
            websocket: Client WebSocket connection
            data: Parsed terminal input message
        """
        run_id = data.get("run_id")
        input_data = data.get("data")

        if not run_id or input_data is None:
            # Don't send error for every keystroke if malformed, just log debug
            logger.debug(
                f"Invalid terminal_input: run_id={run_id}, data_len={len(str(input_data)) if input_data else 0}"
            )
            return

        if not isinstance(input_data, str):
            # input_data must be a string to encode; log and skip non-strings
            logger.debug(
                f"Invalid terminal_input type: run_id={run_id}, data_type={type(input_data).__name__}"
            )
            return

        # Check if this is a tmux PTY bridge streaming_id first
        if hasattr(self, "_tmux_bridge"):
            bridge_fd = await self._tmux_bridge.get_master_fd(run_id)
            if bridge_fd is not None:
                try:
                    encoded_data = input_data.encode("utf-8")
                    await asyncio.to_thread(os.write, bridge_fd, encoded_data)
                except OSError as e:
                    logger.warning(f"Failed to write to tmux bridge {run_id}: {e}")
                return

        registry = get_running_agent_registry()
        # Look up by run_id
        agent = registry.get(run_id)

        if not agent:
            # Be silent on missing agent to avoid spamming errors if frontend is out of sync
            # or if agent just died.
            return

        # Route input to tmux session or PTY
        if agent.tmux_session_name:
            try:
                from gobby.agents.tmux import get_tmux_session_manager

                mgr = get_tmux_session_manager()
                await mgr.send_keys(agent.tmux_session_name, input_data)
            except Exception as e:
                logger.warning(f"Failed to send keys to tmux agent {run_id}: {e}")
            return

        if agent.master_fd is None:
            logger.warning(f"Agent {run_id} has no PTY master_fd")
            return

        try:
            # Write key/input to PTY off the event loop
            encoded_data = input_data.encode("utf-8")
            await asyncio.to_thread(os.write, agent.master_fd, encoded_data)
        except OSError as e:
            logger.warning(f"Failed to write to agent {run_id} PTY: {e}")
