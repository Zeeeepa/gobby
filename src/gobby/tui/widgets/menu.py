"""Menu panel widget for screen navigation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


@dataclass
class MenuItem:
    """A menu item with key binding and label."""

    key: str
    label: str
    screen_id: str


class MenuItemWidget(Static):
    """Individual menu item widget."""

    DEFAULT_CSS = """
    MenuItemWidget {
        height: 3;
        padding: 0 1;
        content-align: left middle;
    }

    MenuItemWidget:hover {
        background: #45475a;
    }

    MenuItemWidget.--selected {
        background: #7c3aed;
        color: white;
        text-style: bold;
    }
    """

    selected = reactive(False)

    def __init__(
        self,
        item: MenuItem,
        selected: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.item = item
        self.selected = selected

    def compose(self) -> ComposeResult:
        yield Static(f"[{self.item.key.upper()}] {self.item.label}")

    def watch_selected(self, selected: bool) -> None:
        self.set_class(selected, "--selected")

    def on_click(self) -> None:
        self.post_message(MenuPanel.ItemSelected(self.item))


class MenuPanel(Widget):
    """Left sidebar menu panel with keyboard navigation."""

    DEFAULT_CSS = """
    MenuPanel {
        width: 14;
        background: #313244;
        border-right: solid #45475a;
    }
    """

    MENU_ITEMS = [
        MenuItem("d", "Dashboard", "dashboard"),
        MenuItem("t", "Tasks", "tasks"),
        MenuItem("s", "Sessions", "sessions"),
        MenuItem("c", "Chat", "chat"),
        MenuItem("a", "Agents", "agents"),
        MenuItem("w", "Worktrees", "worktrees"),
        MenuItem("f", "Workflows", "workflows"),
        MenuItem("m", "Memory", "memory"),
        MenuItem("e", "Metrics", "metrics"),
        MenuItem("o", "Orchestrator", "orchestrator"),
    ]

    current_screen = reactive("dashboard")

    @dataclass
    class ItemSelected(Message):
        """Message sent when a menu item is selected."""

        item: MenuItem

    def compose(self) -> ComposeResult:
        with Vertical():
            for item in self.MENU_ITEMS:
                yield MenuItemWidget(
                    item,
                    selected=(item.screen_id == self.current_screen),
                    id=f"menu-{item.screen_id}",
                )

    def watch_current_screen(self, screen_id: str) -> None:
        """Update selected state when current screen changes."""
        # Skip if not yet composed
        if not self.is_mounted:
            return
        for item in self.MENU_ITEMS:
            try:
                widget = self.query_one(f"#menu-{item.screen_id}", MenuItemWidget)
                widget.selected = item.screen_id == screen_id
            except NoMatches:
                pass  # Widget not yet mounted

    def select_screen(self, screen_id: str) -> None:
        """Programmatically select a screen."""
        self.current_screen = screen_id
        for item in self.MENU_ITEMS:
            if item.screen_id == screen_id:
                self.post_message(self.ItemSelected(item))
                break

    def get_key_bindings(self) -> dict[str, str]:
        """Return key -> screen_id mapping for binding setup."""
        return {item.key: item.screen_id for item in self.MENU_ITEMS}
