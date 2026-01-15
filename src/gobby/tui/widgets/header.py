"""Header widget with ASCII logo and status."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

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
        height: 8;
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
    """

    def __init__(
        self,
        version: str = "0.2.2",
        view_name: str = "SESSIONS",
        connected: bool = False,
    ) -> None:
        """Initialize the header.

        Args:
            version: Gobby version string
            view_name: Current view name to display
            connected: Whether connected to daemon
        """
        super().__init__()
        self.version = version
        self.view_name = view_name
        self._connected = connected

    def compose(self) -> ComposeResult:
        """Compose the header layout."""
        with Horizontal():
            yield Static(GOBBY_LOGO_MAIN, id="logo")
            with Horizontal(classes="status-container"):
                yield Static(f"[dim]v{self.version}[/]", classes="version")
                status_class = "status-connected" if self._connected else "status-disconnected"
                status_text = "CONNECTED" if self._connected else "DISCONNECTED"
                yield Static(f"[{status_class}]{status_text}[/]", id="daemon-status")
        yield Static(f"[dim]VIEW:[/] [bold]{self.view_name}[/]", classes="view-label")

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
        view_label.update(f"[dim]VIEW:[/] [bold]{view_name}[/]")
