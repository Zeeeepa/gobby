"""Inter-agent message panel widget."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class AgentMessage(Static):
    """A single agent message display."""

    DEFAULT_CSS = """
    AgentMessage {
        height: 1;
        padding: 0 1;
    }

    AgentMessage.--outgoing {
        color: #06b6d4;
    }

    AgentMessage.--incoming {
        color: #cdd6f4;
    }

    AgentMessage .message-arrow {
        width: 2;
    }

    AgentMessage .message-sender {
        color: #a6adc8;
        width: 12;
    }

    AgentMessage .message-content {
        width: 1fr;
    }

    AgentMessage .message-time {
        color: #6c7086;
        width: 8;
    }
    """

    def __init__(
        self,
        sender: str,
        content: str,
        direction: str = "incoming",
        timestamp: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.sender = sender
        self.content = content
        self.direction = direction
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")
        self.add_class(f"--{direction}")

    def compose(self) -> ComposeResult:
        arrow = "→" if self.direction == "outgoing" else "←"
        with Horizontal():
            yield Static(arrow, classes="message-arrow")
            yield Static(f"[{self.sender}]", classes="message-sender")
            yield Static(str(self.content)[:60], classes="message-content")
            yield Static(self.timestamp[-8:], classes="message-time")


class InterAgentMessagePanel(Widget):
    """Panel showing real-time inter-agent messages."""

    DEFAULT_CSS = """
    InterAgentMessagePanel {
        height: 1fr;
        border: round #45475a;
    }

    InterAgentMessagePanel .panel-header {
        height: 1;
        padding: 0 1;
        background: #313244;
    }

    InterAgentMessagePanel .panel-title {
        text-style: bold;
        color: #a78bfa;
    }

    InterAgentMessagePanel .messages-scroll {
        height: 1fr;
        padding: 1;
    }

    InterAgentMessagePanel .empty-state {
        content-align: center middle;
        height: 1fr;
        color: #6c7086;
    }
    """

    messages: reactive[list[dict[str, Any]]] = reactive(list)
    max_messages = 100

    def compose(self) -> ComposeResult:
        yield Static("💬 Inter-Agent Messages", classes="panel-header panel-title")

        if not self.messages:
            yield Static("No messages yet", classes="empty-state")
        else:
            with VerticalScroll(classes="messages-scroll", id="messages-scroll"):
                for msg in self.messages[-20:]:  # Show last 20
                    yield AgentMessage(
                        sender=msg.get("sender", "unknown"),
                        content=msg.get("content", ""),
                        direction=msg.get("direction", "incoming"),
                        timestamp=msg.get("timestamp"),
                    )

    def watch_messages(self, messages: list[dict[str, Any]]) -> None:
        """Scroll to bottom when messages change."""
        # Schedule scroll after recompose completes
        self.call_after_refresh(self._scroll_to_end)

    def _scroll_to_end(self) -> None:
        """Scroll the message panel to the end."""
        try:
            scroll = self.query_one("#messages-scroll", VerticalScroll)
            scroll.scroll_end(animate=False)
        except Exception:
            pass

    def add_message(
        self,
        sender: str,
        content: str,
        direction: str = "incoming",
    ) -> None:
        """Add a new message to the panel."""
        new_messages = list(self.messages)
        new_messages.append({
            "sender": sender,
            "content": content,
            "direction": direction,
            "timestamp": datetime.now().isoformat(),
        })

        # Keep only the last max_messages - reactive will trigger recompose
        self.messages = new_messages[-self.max_messages:]

    def clear_messages(self) -> None:
        """Clear all messages."""
        self.messages = []
