"""Command input widget for user commands."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, Static


class CommandInput(Static):
    """Command input widget with prompt."""

    DEFAULT_CSS = """
    CommandInput {
        height: 3;
        dock: bottom;
        background: #0C0C0C;
        border-top: solid #333333;
        padding: 0 1;
    }

    CommandInput Horizontal {
        height: 100%;
        align: left middle;
    }

    CommandInput .prompt {
        color: #6CBF47;
        width: auto;
        padding-right: 1;
    }

    CommandInput Input {
        width: 1fr;
        background: #0C0C0C;
        border: none;
    }

    CommandInput Input:focus {
        border: none;
    }
    """

    class CommandSubmitted(Message):
        """Posted when a command is submitted."""

        def __init__(self, command: str) -> None:
            """Initialize the message.

            Args:
                command: The submitted command string
            """
            self.command = command
            super().__init__()

    def __init__(self, prompt: str = "Command:") -> None:
        """Initialize the command input.

        Args:
            prompt: The prompt text to display
        """
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        """Compose the command input."""
        with Horizontal():
            yield Static(self.prompt, classes="prompt")
            yield Input(
                placeholder="Type a command or 'help'...",
                id="command-input",
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command submission.

        Args:
            event: The input submitted event
        """
        command = event.value.strip()
        if command:
            self.post_message(self.CommandSubmitted(command))
            # Clear the input
            event.input.value = ""

    def focus_input(self) -> None:
        """Focus the command input field."""
        self.query_one("#command-input", Input).focus()
