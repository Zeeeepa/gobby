"""Log panel widget for displaying system messages."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.widgets import RichLog


class LogPanel(RichLog):
    """Scrolling log panel for system messages and events."""

    DEFAULT_CSS = """
    LogPanel {
        height: 8;
        dock: bottom;
        background: #161616;
        border-top: solid #333333;
        padding: 0 1;
    }
    """

    def __init__(self, max_lines: int = 1000) -> None:
        """Initialize the log panel.

        Args:
            max_lines: Maximum number of lines to retain
        """
        super().__init__(
            max_lines=max_lines,
            highlight=True,
            markup=True,
            wrap=True,
        )

    def log_event(self, event_type: str, message: str) -> None:
        """Add a timestamped log entry.

        Args:
            event_type: The event type/category
            message: The log message
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.write(f"[dim]{timestamp}[/] [{event_type}] {message}")

    def log_info(self, message: str) -> None:
        """Log an info message.

        Args:
            message: The message to log
        """
        self.log_event("[#3498DB]INFO[/]", message)

    def log_success(self, message: str) -> None:
        """Log a success message.

        Args:
            message: The message to log
        """
        self.log_event("[#6CBF47]OK[/]", message)

    def log_warning(self, message: str) -> None:
        """Log a warning message.

        Args:
            message: The message to log
        """
        self.log_event("[#F5A623]WARN[/]", message)

    def log_error(self, message: str) -> None:
        """Log an error message.

        Args:
            message: The message to log
        """
        self.log_event("[#E74C3C]ERROR[/]", message)

    def log_websocket(self, event: dict[str, Any]) -> None:
        """Log a WebSocket event.

        Args:
            event: The event dict with 'type' key
        """
        event_type = event.get("type", "unknown")
        data = event.get("data", {})
        summary = str(data)[:50] + "..." if len(str(data)) > 50 else str(data)
        self.log_event("[#9B59B6]WS[/]", f"{event_type}: {summary}")

    def log_session_event(
        self,
        action: str,
        session_id: str,
        provider: str | None = None,
    ) -> None:
        """Log a session-related event.

        Args:
            action: The action (created, updated, expired)
            session_id: The session ID
            provider: The session provider (optional)
        """
        short_id = session_id[:8]
        provider_str = f" [{provider}]" if provider else ""
        self.log_event("[#4ECDC4]SESSION[/]", f"{action}: {short_id}{provider_str}")
