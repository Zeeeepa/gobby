"""WebSocket server package.

Re-exports WebSocketServer and WebSocketConfig for backward compatibility.
"""

from gobby.servers.websocket.models import WebSocketConfig
from gobby.servers.websocket.server import WebSocketServer

__all__ = ["WebSocketConfig", "WebSocketServer"]
