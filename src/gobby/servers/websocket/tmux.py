"""WebSocket handlers for tmux session management.

TmuxMixin provides handlers for listing, attaching, detaching, creating,
killing, and resizing tmux sessions via PTY relay. Follows the HandlerMixin
pattern.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import uuid4

from gobby.agents.registry import get_running_agent_registry
from gobby.agents.tmux.config import TmuxConfig
from gobby.agents.tmux.pty_bridge import TmuxPTYBridge
from gobby.agents.tmux.session_manager import TmuxSessionManager

logger = logging.getLogger(__name__)

# Default server config (no socket = user's default tmux)
_DEFAULT_CONFIG = TmuxConfig(socket_name="")
_GOBBY_CONFIG = TmuxConfig(socket_name="gobby")


class TmuxMixin:
    """Mixin providing tmux session management handlers for WebSocketServer.

    Requires on the host class:
    - ``self.clients: dict[Any, dict[str, Any]]``
    - ``async self.broadcast_terminal_output(run_id, data)`` (from BroadcastMixin)
    - ``async self._send_error(websocket, message, ...)`` (from HandlerMixin)
    """

    clients: dict[Any, dict[str, Any]]

    # These are provided by other mixins (BroadcastMixin, HandlerMixin).
    # Declared as TYPE_CHECKING-only protocol hints to avoid shadowing real methods.
    if TYPE_CHECKING:

        async def broadcast_terminal_output(self, run_id: str, data: str) -> None: ...
        async def _send_error(
            self, websocket: Any, message: str, request_id: str | None = None, code: str = "ERROR"
        ) -> None: ...

    def _init_tmux(self) -> None:
        """Initialize tmux subsystem. Call from WebSocketServer.__init__."""
        self._tmux_bridge = TmuxPTYBridge()
        self._tmux_mgr_gobby = TmuxSessionManager(_GOBBY_CONFIG)
        self._tmux_mgr_default = TmuxSessionManager(_DEFAULT_CONFIG)
        # Track which client owns which bridge (for cleanup on disconnect)
        self._tmux_client_bridges: dict[Any, set[str]] = {}  # websocket -> {streaming_id}

    async def _cleanup_tmux(self) -> None:
        """Clean up all tmux bridges. Call from WebSocketServer.stop."""
        from gobby.agents.pty_reader import get_pty_reader_manager

        reader = get_pty_reader_manager()
        for streaming_id in list((await self._tmux_bridge.list_bridges()).keys()):
            await reader.stop_reader(streaming_id)
            await self._tmux_bridge.detach(streaming_id)
        self._tmux_client_bridges.clear()

    async def _cleanup_tmux_client(self, websocket: Any) -> None:
        """Clean up bridges owned by a disconnecting client."""
        from gobby.agents.pty_reader import get_pty_reader_manager

        bridge_ids = self._tmux_client_bridges.pop(websocket, set())
        if not bridge_ids:
            return

        reader = get_pty_reader_manager()
        for streaming_id in bridge_ids:
            await reader.stop_reader(streaming_id)
            await self._tmux_bridge.detach(streaming_id)
            logger.debug(f"Cleaned up tmux bridge {streaming_id} for disconnected client")

    def _get_tmux_manager(self, socket: str) -> TmuxSessionManager:
        """Get the session manager for a given socket."""
        if socket == "gobby":
            return self._tmux_mgr_gobby
        return self._tmux_mgr_default

    def _get_tmux_config(self, socket: str) -> TmuxConfig:
        """Get the config for a given socket."""
        if socket == "gobby":
            return _GOBBY_CONFIG
        return _DEFAULT_CONFIG

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_tmux_list_sessions(self, websocket: Any, data: dict[str, Any]) -> None:
        """List tmux sessions from both default and gobby servers."""
        request_id = data.get("request_id")

        sessions: list[dict[str, Any]] = []
        registry = get_running_agent_registry()

        for socket_name, mgr in [
            ("default", self._tmux_mgr_default),
            ("gobby", self._tmux_mgr_gobby),
        ]:
            try:
                tmux_sessions = await mgr.list_sessions()
                for s in tmux_sessions:
                    # Check if this session is managed by an agent
                    agent_managed = False
                    agent_run_id = None
                    for agent in registry.list_all():
                        if agent.tmux_session_name == s.name:
                            agent_managed = True
                            agent_run_id = agent.run_id
                            break

                    # Check if a bridge is active for this session
                    attached_bridge = None
                    bridges = await self._tmux_bridge.list_bridges()
                    for sid, bridge in bridges.items():
                        if (
                            bridge.session_name == s.name
                            and bridge.socket_name == mgr.config.socket_name
                        ):
                            attached_bridge = sid
                            break

                    sessions.append(
                        {
                            "name": s.name,
                            "socket": socket_name,
                            "pane_pid": s.pane_pid,
                            "agent_managed": agent_managed,
                            "agent_run_id": agent_run_id,
                            "attached_bridge": attached_bridge,
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to list {socket_name} tmux sessions: {e}")

        response: dict[str, Any] = {
            "type": "tmux_sessions_list",
            "sessions": sessions,
        }
        if request_id:
            response["request_id"] = request_id

        await websocket.send(json.dumps(response))

    async def _handle_tmux_attach(self, websocket: Any, data: dict[str, Any]) -> None:
        """Attach to a tmux session via PTY relay."""
        from gobby.agents.pty_reader import get_pty_reader_manager

        request_id = data.get("request_id")
        session_name = data.get("session_name")
        socket = data.get("socket", "default")

        if not session_name:
            await self._send_error(websocket, "Missing session_name", request_id=request_id)
            return

        config = self._get_tmux_config(socket)
        mgr = self._get_tmux_manager(socket)

        # Verify session exists
        if not await mgr.has_session(session_name):
            await self._send_error(
                websocket, f"Session '{session_name}' not found", request_id=request_id
            )
            return

        streaming_id = f"tmux-{uuid4().hex[:12]}"

        try:
            master_fd = await self._tmux_bridge.attach(
                session_name=session_name,
                streaming_id=streaming_id,
                config=config,
            )

            # Start PTY reader on the bridge's master_fd
            reader = get_pty_reader_manager()

            # Create a lightweight RunningAgent-like object for the reader
            class _BridgeAgent(NamedTuple):
                run_id: str
                master_fd: int

            await reader.start_reader(_BridgeAgent(streaming_id, master_fd))  # type: ignore[arg-type]

            # Track ownership for cleanup
            if websocket not in self._tmux_client_bridges:
                self._tmux_client_bridges[websocket] = set()
            self._tmux_client_bridges[websocket].add(streaming_id)

            response: dict[str, Any] = {
                "type": "tmux_attach_result",
                "success": True,
                "streaming_id": streaming_id,
                "session_name": session_name,
                "socket": socket,
            }
            if request_id:
                response["request_id"] = request_id

            await websocket.send(json.dumps(response))

            # Hide tmux status bar in web terminal view
            try:
                args: list[str] = [config.command]
                if config.socket_name:
                    args.extend(["-L", config.socket_name])
                args.extend(["set-option", "-t", session_name, "status", "off"])
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except Exception:  # nosec B110 — status bar is cosmetic
                pass

        except Exception as e:
            logger.error(f"Failed to attach tmux session '{session_name}': {e}")
            await self._send_error(websocket, f"Attach failed: {e}", request_id=request_id)

    async def _handle_tmux_detach(self, websocket: Any, data: dict[str, Any]) -> None:
        """Detach from a tmux session (close PTY bridge)."""
        from gobby.agents.pty_reader import get_pty_reader_manager

        request_id = data.get("request_id")
        streaming_id = data.get("streaming_id")

        if not streaming_id:
            await self._send_error(websocket, "Missing streaming_id", request_id=request_id)
            return

        reader = get_pty_reader_manager()
        await reader.stop_reader(streaming_id)
        await self._tmux_bridge.detach(streaming_id)

        # Remove from client tracking
        client_bridges = self._tmux_client_bridges.get(websocket)
        if client_bridges:
            client_bridges.discard(streaming_id)

        response: dict[str, Any] = {
            "type": "tmux_detach_result",
            "success": True,
            "streaming_id": streaming_id,
        }
        if request_id:
            response["request_id"] = request_id

        await websocket.send(json.dumps(response))

    async def _handle_tmux_create_session(self, websocket: Any, data: dict[str, Any]) -> None:
        """Create a new tmux session."""
        request_id = data.get("request_id")
        name = data.get("name")
        command = data.get("command")
        cwd = data.get("cwd")
        socket = data.get("socket", "default")

        mgr = self._get_tmux_manager(socket)

        if not mgr.is_available():
            await self._send_error(websocket, "tmux is not installed", request_id=request_id)
            return

        try:
            session_name = name or f"web-{uuid4().hex[:8]}"
            info = await mgr.create_session(
                name=session_name,
                command=command,
                cwd=cwd,
            )

            # Broadcast session event
            await self._broadcast_tmux_event("session_created", info.name, socket)

            response: dict[str, Any] = {
                "type": "tmux_create_result",
                "success": True,
                "session_name": info.name,
                "pane_pid": info.pane_pid,
                "socket": socket,
            }
            if request_id:
                response["request_id"] = request_id

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Failed to create tmux session: {e}")
            await self._send_error(websocket, f"Create failed: {e}", request_id=request_id)

    async def _handle_tmux_kill_session(self, websocket: Any, data: dict[str, Any]) -> None:
        """Kill a tmux session."""
        request_id = data.get("request_id")
        session_name = data.get("session_name")
        socket = data.get("socket", "default")

        if not session_name:
            await self._send_error(websocket, "Missing session_name", request_id=request_id)
            return

        # Refuse to kill agent-managed sessions
        registry = get_running_agent_registry()
        for agent in registry.list_all():
            if agent.tmux_session_name == session_name:
                await self._send_error(
                    websocket,
                    f"Session '{session_name}' is managed by agent {agent.run_id}",
                    request_id=request_id,
                    code="AGENT_MANAGED",
                )
                return

        # Detach any bridges to this session first
        from gobby.agents.pty_reader import get_pty_reader_manager

        reader = get_pty_reader_manager()
        mgr = self._get_tmux_manager(socket)

        bridges = await self._tmux_bridge.list_bridges()
        for sid, bridge in list(bridges.items()):
            if bridge.session_name == session_name and bridge.socket_name == mgr.config.socket_name:
                await reader.stop_reader(sid)
                await self._tmux_bridge.detach(sid)
                # Clean from all client tracking
                for client_set in self._tmux_client_bridges.values():
                    client_set.discard(sid)

        try:
            success = await mgr.kill_session(session_name)
            if success:
                await self._broadcast_tmux_event("session_killed", session_name, socket)

            response: dict[str, Any] = {
                "type": "tmux_kill_result",
                "success": success,
                "session_name": session_name,
            }
            if request_id:
                response["request_id"] = request_id

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Failed to kill tmux session '{session_name}': {e}")
            await self._send_error(websocket, f"Kill failed: {e}", request_id=request_id)

    async def _handle_tmux_resize(self, websocket: Any, data: dict[str, Any]) -> None:
        """Resize PTY for an attached tmux session."""
        streaming_id = data.get("streaming_id")
        rows = data.get("rows")
        cols = data.get("cols")

        if not streaming_id or not rows or not cols:
            return  # Silent failure for resize events

        await self._tmux_bridge.resize(streaming_id, int(rows), int(cols))

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    async def _broadcast_tmux_event(self, event: str, session_name: str, socket: str) -> None:
        """Broadcast a tmux session lifecycle event to subscribed clients."""
        if not self.clients:
            return

        from datetime import UTC, datetime

        from websockets.exceptions import ConnectionClosed

        message = json.dumps(
            {
                "type": "tmux_session_event",
                "event": event,
                "session_name": session_name,
                "socket": socket,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        for ws in list(self.clients.keys()):
            try:
                subs = getattr(ws, "subscriptions", None)
                if subs is not None:
                    if "tmux_session_event" not in subs and "*" not in subs:
                        continue
                await ws.send(message)
            except ConnectionClosed:
                pass
            except Exception as e:
                logger.warning(f"Tmux event broadcast failed: {e}")
