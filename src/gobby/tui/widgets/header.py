"""Header widget with ASCII logo and status."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Static

# ASCII logo with shadow effect rendered via Rich markup
GOBBY_LOGO = """\
[#2d5a1f] ██████   ██████  ██████  ██████  ██    ██[/]
[#2d5a1f]██       ██    ██ ██   ██ ██   ██  ██  ██[/]
[#2d5a1f]██   ███ ██    ██ ██████  ██████    ████[/]
[#2d5a1f]██    ██ ██    ██ ██   ██ ██   ██    ██[/]
[#2d5a1f] ██████   ██████  ██████  ██████     ██[/]"""

GOBBY_LOGO_MAIN = """\
[#6CBF47 bold] ██████   ██████  ██████  ██████  ██    ██[/]
[#6CBF47 bold]██       ██    ██ ██   ██ ██   ██  ██  ██[/]
[#6CBF47 bold]██   ███ ██    ██ ██████  ██████    ████[/]
[#6CBF47 bold]██    ██ ██    ██ ██   ██ ██   ██    ██[/]
[#6CBF47 bold] ██████   ██████  ██████  ██████     ██[/]"""


class GobbyHeader(Static):
    """Header widget displaying the Gobby ASCII logo and daemon status."""

    DEFAULT_CSS = """
    GobbyHeader {
        height: 11;
        dock: top;
        background: #161616;
        border-bottom: solid #333333;
        padding: 1 2 0 2;
    }

    GobbyHeader .logo-container {
        width: 1fr;
    }

    GobbyHeader .status-container {
        width: auto;
        align: right middle;
        padding-right: 2;
    }

    GobbyHeader .version {
        color: #666666;
    }

    GobbyHeader .status-connected {
        color: #6CBF47;
    }

    GobbyHeader .status-disconnected {
        color: #E74C3C;
    }

    GobbyHeader .view-label {
        color: #666666;
        padding-left: 2;
    }

    GobbyHeader .filter-row {
        height: 3;
        align: left middle;
        padding: 0 0 0 2;
    }

    GobbyHeader .filter-row Button {
        min-width: 10;
        margin: 0 1 0 0;
        background: #252525;
        border: none;
        height: 1;
    }

    GobbyHeader .filter-row Button:hover {
        background: #333333;
    }

    GobbyHeader .filter-row Button.selected {
        background: #6CBF47;
        color: #0C0C0C;
        text-style: bold;
    }
    """

    def __init__(
        self,
        version: str = "0.2.2",
        view_name: str = "SESSIONS",
        connected: bool = False,
        filters: list[str] | None = None,
        default_filter: str = "active",
    ) -> None:
        """Initialize the header.

        Args:
            version: Gobby version string
            view_name: Current view name to display
            connected: Whether connected to daemon
            filters: List of filter options
            default_filter: Default selected filter
        """
        super().__init__()
        self.version = version
        self.view_name = view_name
        self._connected = connected
        self.filters = filters or ["Active", "Expired", "All"]
        self.selected_filter = default_filter.lower()

    def compose(self) -> ComposeResult:
        """Compose the header layout."""
        with Horizontal():
            yield Static(GOBBY_LOGO_MAIN, id="logo")
            with Horizontal(classes="status-container"):
                yield Static(f"[dim]v{self.version}[/]", classes="version")
                # Use actual Rich color codes instead of CSS class names
                status_style = "#6CBF47" if self._connected else "#E74C3C"
                status_text = "CONNECTED" if self._connected else "DISCONNECTED"
                yield Static(f"[{status_style}]{status_text}[/]", id="daemon-status")
        with Horizontal(classes="filter-row"):
            yield Static(f"[dim]VIEW:[/] [bold]{self.view_name}[/]  ", classes="view-label")
            for filter_name in self.filters:
                filter_id = f"filter-{filter_name.lower()}"
                classes = "selected" if filter_name.lower() == self.selected_filter else ""
                yield Button(filter_name, id=filter_id, classes=classes)

    def set_connected(self, connected: bool) -> None:
        """Update connection status.

        Args:
            connected: New connection state
        """
        self._connected = connected
        status_widget = self.query_one("#daemon-status", Static)
        if connected:
            status_widget.update("[#6CBF47]CONNECTED[/]")
        else:
            status_widget.update("[#E74C3C]DISCONNECTED[/]")

    def set_view(self, view_name: str) -> None:
        """Update the current view name.

        Args:
            view_name: New view name to display
        """
        self.view_name = view_name
        view_label = self.query_one(".view-label", Static)
        view_label.update(f"[dim]VIEW:[/] [bold]{view_name}[/]  ")

    class FilterChanged(Message):
        """Posted when filter selection changes."""

        def __init__(self, filter_value: str) -> None:
            self.filter_value = filter_value
            super().__init__()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle filter button press."""
        # Update selected state visually
        for btn in self.query(Button):
            btn.remove_class("selected")
        event.button.add_class("selected")

        # Extract filter value from button id
        button_id = event.button.id or ""
        filter_value = button_id.replace("filter-", "")
        self.selected_filter = filter_value

        # Post message for parent to handle
        self.post_message(self.FilterChanged(filter_value))
