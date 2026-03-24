"""WebSocket handler modules.

HandlerMixin provides individual message type handlers for WebSocketServer.
Sub-modules group related session-control handlers as async functions
dispatched by SessionControlMixin.
"""

from gobby.servers.websocket.handlers.core import HandlerMixin

__all__ = ["HandlerMixin"]
