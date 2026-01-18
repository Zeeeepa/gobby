"""Chat widgets for LLM interface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Static, TextArea


class ChatMessage(Static):
    """A single chat message display."""

    DEFAULT_CSS = """
    ChatMessage {
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }

    ChatMessage.--user {
        margin-left: 8;
        background: #313244;
        border: round #06b6d4;
    }

    ChatMessage.--assistant {
        margin-right: 8;
        background: #313244;
        border: round #7c3aed;
    }

    ChatMessage.--system {
        margin-left: 4;
        margin-right: 4;
        background: #45475a;
        border: round #6c7086;
    }

    ChatMessage .message-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 1;
    }

    ChatMessage .message-sender {
        text-style: bold;
        width: 1fr;
    }

    ChatMessage.--user .message-sender {
        color: #06b6d4;
    }

    ChatMessage.--assistant .message-sender {
        color: #a78bfa;
    }

    ChatMessage.--system .message-sender {
        color: #6c7086;
    }

    ChatMessage .message-time {
        color: #6c7086;
        width: auto;
    }

    ChatMessage .message-content {
        color: #cdd6f4;
    }
    """

    def __init__(
        self,
        sender: str,
        content: str,
        role: str = "user",
        timestamp: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.sender = sender
        self.content = content
        self.role = role
        self.timestamp = timestamp or datetime.now().strftime("%H:%M")
        self.add_class(f"--{role}")

    def compose(self) -> ComposeResult:
        with Horizontal(classes="message-header"):
            yield Static(self.sender, classes="message-sender")
            yield Static(self.timestamp, classes="message-time")
        yield Static(self.content, classes="message-content")


class ChatHistory(VerticalScroll):
    """Scrollable chat history container."""

    DEFAULT_CSS = """
    ChatHistory {
        height: 1fr;
        padding: 1;
        background: #1e1e2e;
    }
    """

    messages: reactive[list[dict[str, Any]]] = reactive(list)

    def add_message(
        self,
        sender: str,
        content: str,
        role: str = "user",
        timestamp: str | None = None,
    ) -> None:
        """Add a new message to the chat history."""
        # Store message data
        new_messages = list(self.messages)
        new_messages.append(
            {
                "sender": sender,
                "content": content,
                "role": role,
                "timestamp": timestamp or datetime.now().strftime("%H:%M"),
            }
        )
        self.messages = new_messages

        # Mount the widget
        message = ChatMessage(sender, content, role, timestamp)
        self.mount(message)
        self.scroll_end(animate=False)

    def clear_history(self) -> None:
        """Clear all messages."""
        self.messages = []
        self.remove_children()


class ChatInput(Widget):
    """Chat input widget with send button."""

    DEFAULT_CSS = """
    ChatInput {
        height: auto;
        min-height: 4;
        max-height: 10;
        padding: 1;
        border-top: solid #45475a;
        background: #313244;
    }

    ChatInput .input-row {
        layout: horizontal;
        height: auto;
    }

    ChatInput #message-input {
        width: 1fr;
        height: auto;
        min-height: 3;
        margin-right: 1;
    }

    ChatInput #send-button {
        width: 10;
        height: 3;
    }
    """

    @dataclass
    class Submitted(Message):
        """Message sent when user submits input."""

        text: str

    def compose(self) -> ComposeResult:
        with Horizontal(classes="input-row"):
            yield TextArea(id="message-input")
            yield Button("Send", variant="primary", id="send-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle send button press."""
        if event.button.id == "send-button":
            self._submit()

    def _submit(self) -> None:
        """Submit the current input."""
        text_area = self.query_one("#message-input", TextArea)
        text = text_area.text.strip()
        if text:
            self.post_message(self.Submitted(text))
            text_area.clear()

    def get_text(self) -> str:
        """Get the current input text."""
        return self.query_one("#message-input", TextArea).text

    def clear(self) -> None:
        """Clear the input."""
        self.query_one("#message-input", TextArea).clear()

    def focus_input(self) -> None:
        """Focus the input field."""
        self.query_one("#message-input", TextArea).focus()
