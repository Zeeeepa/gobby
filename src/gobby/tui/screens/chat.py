"""Chat screen for LLM interface with conductor."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.events import Key
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    LoadingIndicator,
    Select,
    Static,
    TextArea,
)

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.ws_client import GobbyWebSocketClient


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

    ChatMessage.--conductor {
        margin-right: 8;
        background: #313244;
        border: round #7c3aed;
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

    ChatMessage .message-time {
        color: #6c7086;
        width: auto;
    }

    ChatMessage.--user .message-sender {
        color: #06b6d4;
    }

    ChatMessage.--conductor .message-sender {
        color: #a78bfa;
    }

    ChatMessage .message-content {
        color: #cdd6f4;
    }
    """

    def __init__(
        self,
        sender: str,
        content: str,
        is_user: bool = True,
        timestamp: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.sender = sender
        self.content = content
        self.is_user = is_user
        self.timestamp = timestamp or datetime.now().strftime("%H:%M")
        self.add_class("--user" if is_user else "--conductor")

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

    def add_message(
        self,
        sender: str,
        content: str,
        is_user: bool = True,
        timestamp: str | None = None,
    ) -> None:
        """Add a new message to the chat history."""
        message = ChatMessage(sender, content, is_user, timestamp)
        self.mount(message)
        # Scroll to bottom
        self.scroll_end(animate=False)


class ChatInputArea(Widget):
    """Input area for composing chat messages."""

    DEFAULT_CSS = """
    ChatInputArea {
        height: auto;
        min-height: 4;
        max-height: 10;
        padding: 1;
        border-top: solid #45475a;
        background: #313244;
    }

    ChatInputArea .input-row {
        layout: horizontal;
        height: auto;
    }

    ChatInputArea #chat-input {
        width: 1fr;
        height: auto;
        min-height: 3;
        margin-right: 1;
    }

    ChatInputArea #send-button {
        width: 10;
        height: 3;
    }

    ChatInputArea .mode-row {
        layout: horizontal;
        height: 1;
        margin-top: 1;
    }

    ChatInputArea .mode-label {
        color: #a6adc8;
        width: auto;
        margin-right: 1;
    }

    ChatInputArea #mode-select {
        width: 20;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(classes="input-row"):
            yield TextArea(id="chat-input")
            yield Button("Send", variant="primary", id="send-button")
        with Horizontal(classes="mode-row"):
            yield Static("Mode:", classes="mode-label")
            yield Select(
                [(label, value) for label, value in [
                    ("Haiku", "haiku"),
                    ("Prose", "prose"),
                    ("Terse", "terse"),
                ]],
                value="haiku",
                id="mode-select",
            )

    def get_message(self) -> str:
        """Get the current message text."""
        text_area = self.query_one("#chat-input", TextArea)
        return text_area.text

    def clear_input(self) -> None:
        """Clear the input field."""
        text_area = self.query_one("#chat-input", TextArea)
        text_area.clear()

    def get_mode(self) -> str:
        """Get the current response mode."""
        select = self.query_one("#mode-select", Select)
        return str(select.value)


class ChatScreen(Widget):
    """Chat screen for interacting with the conductor LLM."""

    DEFAULT_CSS = """
    ChatScreen {
        width: 1fr;
        height: 1fr;
        layout: vertical;
    }

    ChatScreen .chat-header {
        height: 3;
        padding: 1;
        background: #313244;
        border-bottom: solid #45475a;
    }

    ChatScreen .header-title {
        text-style: bold;
        color: #a78bfa;
    }

    ChatScreen .header-mode {
        color: #a6adc8;
        dock: right;
    }

    ChatScreen #chat-history {
        height: 1fr;
    }

    ChatScreen #chat-input-area {
        height: auto;
    }

    ChatScreen .loading-indicator {
        height: 3;
        content-align: center middle;
        background: #313244;
    }
    """

    sending = reactive(False)
    messages: reactive[list[dict[str, Any]]] = reactive(list)

    def __init__(
        self,
        api_client: GobbyAPIClient,
        ws_client: GobbyWebSocketClient,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.api_client = api_client
        self.ws_client = ws_client

    def compose(self) -> ComposeResult:
        with Horizontal(classes="chat-header"):
            yield Static("💬 Chat with Conductor", classes="header-title")
        yield ChatHistory(id="chat-history")
        if self.sending:
            with Container(classes="loading-indicator"):
                yield LoadingIndicator()
        yield ChatInputArea(id="chat-input-area")

    async def on_mount(self) -> None:
        """Initialize the chat screen."""
        # Add welcome message
        history = self.query_one("#chat-history", ChatHistory)
        history.add_message(
            "Conductor",
            "Welcome to Gobby Chat. Ask me about tasks, status, or give commands.",
            is_user=False,
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle send button press."""
        if event.button.id == "send-button":
            await self._send_message()

    async def on_key(self, event: Key) -> None:
        """Handle key events for sending messages."""
        # Check for Enter key in text area (without shift)
        # In Textual, Shift+Enter would be key="shift+enter", not "enter"
        if event.key == "enter":
            # Check if focus is on the text area
            input_area = self.query_one("#chat-input-area", ChatInputArea)
            text_area = input_area.query_one("#chat-input", TextArea)
            if text_area.has_focus:
                event.stop()
                await self._send_message()

    async def _send_message(self) -> None:
        """Send a message to the conductor."""
        input_area = self.query_one("#chat-input-area", ChatInputArea)
        message = input_area.get_message().strip()

        if not message:
            return

        # Add user message to history
        history = self.query_one("#chat-history", ChatHistory)
        history.add_message("You", message, is_user=True)
        input_area.clear_input()

        # Show loading state
        self.sending = True
        await self.recompose()

        try:
            # Get response mode
            mode = input_area.get_mode()

            # Send to conductor (via LLM service)
            response = await self._get_conductor_response(message, mode)

            # Add conductor response
            history.add_message("Conductor", response, is_user=False)

        except Exception as e:
            history.add_message(
                "System",
                f"Error: {e}",
                is_user=False,
            )
        finally:
            self.sending = False
            await self.recompose()

    async def _get_conductor_response(self, message: str, mode: str) -> str:
        """Get a response from the conductor LLM."""
        # Build prompt based on mode
        # Note: system_prompt would be used in full LLM implementation
        # For now, we use simple pattern matching in _generate_response

        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                # Get current status for context
                status = await client.get_status()

                # Build context
                tasks_info = status.get("tasks", {})
                agents_info = await client.list_agents()

                context = f"""System Status:
- Open tasks: {tasks_info.get('open', 0)}
- In progress: {tasks_info.get('in_progress', 0)}
- Running agents: {len([a for a in agents_info if a.get('status') == 'running'])}
"""

                # For now, generate a simple response
                # In a full implementation, this would call the LLM service
                response = await self._generate_response(message, mode, context, tasks_info)
                return response

        except Exception as e:
            raise Exception(f"Failed to get response: {e}") from e

    async def _generate_response(
        self,
        message: str,
        mode: str,
        context: str,
        tasks_info: dict[str, Any],
    ) -> str:
        """Generate a response based on the message and mode."""
        message_lower = message.lower()

        # Simple pattern matching for common queries
        # In production, this would use an actual LLM

        if "status" in message_lower or "what" in message_lower:
            open_count = tasks_info.get("open", 0)
            in_progress = tasks_info.get("in_progress", 0)

            if mode == "haiku":
                if in_progress > 0:
                    return f"{in_progress} task{'s' if in_progress != 1 else ''} in progress\nCode flows through busy hands\nWork carries on"
                elif open_count > 0:
                    return f"{open_count} tasks await you\nReady for your attention\nChoose and begin"
                else:
                    return "All is quiet now\nNo tasks need attention here\nRest or create more"
            elif mode == "terse":
                return f"Open: {open_count}, In Progress: {in_progress}"
            else:
                return f"Currently there are {open_count} open tasks and {in_progress} in progress. Use `/gobby-tasks` to see details or ask me to suggest the next task."

        elif "next" in message_lower or "suggest" in message_lower:
            if mode == "haiku":
                return "Check the task queue now\nPriority guides your path\nBegin with the first"
            else:
                return "I recommend checking the Tasks screen (press T) to see prioritized tasks. The suggest_next_task tool can help identify what to work on next."

        elif "autonomous" in message_lower or "auto" in message_lower:
            if mode == "haiku":
                return "Autonomous mode\nI work while you observe\nTrust but verify"
            else:
                return "To enable autonomous mode, use the Orchestrator screen (press O) and toggle the mode. I'll work through tasks independently and pause for reviews when needed."

        elif "help" in message_lower:
            if mode == "haiku":
                return "Ask me anything\nTasks, status, or guidance\nI am here to help"
            else:
                return "I can help you with:\n- Checking task and agent status\n- Explaining system state\n- Suggesting next tasks\n- Enabling autonomous mode\n\nJust ask!"

        else:
            # Default response
            if mode == "haiku":
                return "Your words reach my ears\nBut meaning escapes me now\nPlease ask once more"
            else:
                return "I'm not sure how to help with that specific request. Try asking about task status, next tasks, or system state. You can also use the other screens (D/T/S/A/O) for direct interaction."

    def on_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle WebSocket events."""
        # Show relevant events in chat
        try:
            history = self.query_one("#chat-history", ChatHistory)

            if event_type == "autonomous_event":
                event = data.get("event", "")
                task_id = data.get("task_id", "")
                history.add_message(
                    "System",
                    f"Autonomous: {event} ({task_id})",
                    is_user=False,
                )

            elif event_type == "agent_event":
                event = data.get("event", "")
                run_id = data.get("run_id", "")[:8]
                if event in ["agent_started", "agent_completed", "agent_failed"]:
                    history.add_message(
                        "System",
                        f"Agent {run_id}: {event}",
                        is_user=False,
                    )

        except Exception:
            pass

    def activate_search(self) -> None:
        """Focus the chat input."""
        try:
            input_area = self.query_one("#chat-input-area", ChatInputArea)
            text_area = input_area.query_one("#chat-input", TextArea)
            text_area.focus()
        except Exception:
            pass
