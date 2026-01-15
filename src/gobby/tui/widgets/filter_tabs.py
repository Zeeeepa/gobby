"""Filter tabs widget for view filtering."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Static


class FilterTabs(Static):
    """Filter tabs for Active/Expired/All selection."""

    DEFAULT_CSS = """
    FilterTabs {
        height: 3;
        dock: top;
        background: #0C0C0C;
        padding: 0 2;
    }

    FilterTabs Horizontal {
        height: 100%;
        align: left middle;
    }

    FilterTabs Button {
        min-width: 10;
        margin: 0 1;
        background: #161616;
        border: none;
    }

    FilterTabs Button:hover {
        background: #252525;
    }

    FilterTabs Button.selected {
        background: #6CBF47;
        color: #0C0C0C;
    }

    FilterTabs Button.selected:hover {
        background: #7DCF58;
    }
    """

    class FilterChanged(Message):
        """Posted when filter selection changes."""

        def __init__(self, filter_value: str) -> None:
            """Initialize the message.

            Args:
                filter_value: The new filter value
            """
            self.filter_value = filter_value
            super().__init__()

    def __init__(
        self,
        filters: list[str] | None = None,
        default: str = "active",
    ) -> None:
        """Initialize filter tabs.

        Args:
            filters: List of filter options (default: Active/Expired/All)
            default: Default selected filter
        """
        super().__init__()
        self.filters = filters or ["Active", "Expired", "All"]
        self.selected = default.lower()

    def compose(self) -> ComposeResult:
        """Compose the filter tabs."""
        with Horizontal():
            for filter_name in self.filters:
                filter_id = f"filter-{filter_name.lower()}"
                classes = "selected" if filter_name.lower() == self.selected else ""
                yield Button(filter_name, id=filter_id, classes=classes)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press to update selection.

        Args:
            event: The button pressed event
        """
        # Update selected state visually
        for btn in self.query(Button):
            btn.remove_class("selected")
        event.button.add_class("selected")

        # Extract filter value from button id
        button_id = event.button.id or ""
        filter_value = button_id.replace("filter-", "")
        self.selected = filter_value

        # Post message for parent to handle
        self.post_message(self.FilterChanged(filter_value))

    def set_filter(self, filter_value: str) -> None:
        """Programmatically set the filter.

        Args:
            filter_value: The filter to select
        """
        self.selected = filter_value.lower()
        for btn in self.query(Button):
            btn_id = btn.id or ""
            if btn_id == f"filter-{self.selected}":
                btn.add_class("selected")
            else:
                btn.remove_class("selected")
