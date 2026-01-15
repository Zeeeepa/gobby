"""Status footer widget."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class StatusFooter(Static):
    """Footer widget showing mode, git branch, and scroll percentage."""

    DEFAULT_CSS = """
    StatusFooter {
        height: 1;
        dock: bottom;
        background: #161616;
        padding: 0 1;
    }

    StatusFooter Horizontal {
        width: 100%;
    }

    StatusFooter .mode {
        color: #6CBF47;
        text-style: bold;
        width: auto;
        padding-right: 2;
    }

    StatusFooter .branch {
        color: #3498DB;
        width: auto;
        padding-right: 2;
    }

    StatusFooter .spacer {
        width: 1fr;
    }

    StatusFooter .percentage {
        color: #666666;
        width: auto;
    }
    """

    def __init__(
        self,
        mode: str = "NORMAL",
        branch: str = "main",
        percentage: int = 100,
    ) -> None:
        """Initialize the footer.

        Args:
            mode: Current mode (NORMAL, INSERT, etc.)
            branch: Current git branch
            percentage: Scroll percentage
        """
        super().__init__()
        self._mode = mode
        self._branch = branch
        self._percentage = percentage

    def compose(self) -> ComposeResult:
        """Compose the footer layout."""
        with Horizontal():
            yield Static(self._mode, classes="mode", id="mode")
            yield Static(self._branch, classes="branch", id="branch")
            yield Static("", classes="spacer")
            yield Static(f"{self._percentage}%", classes="percentage", id="percentage")

    def set_mode(self, mode: str) -> None:
        """Update the mode display.

        Args:
            mode: New mode string
        """
        self._mode = mode
        self.query_one("#mode", Static).update(mode)

    def set_branch(self, branch: str) -> None:
        """Update the branch display.

        Args:
            branch: New branch name
        """
        self._branch = branch
        self.query_one("#branch", Static).update(branch)

    def set_percentage(self, percentage: int) -> None:
        """Update the scroll percentage.

        Args:
            percentage: New percentage (0-100)
        """
        self._percentage = percentage
        self.query_one("#percentage", Static).update(f"{percentage}%")
