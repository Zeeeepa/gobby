"""Conductor widgets for haiku display and mode indicator."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class HaikuDisplay(Widget):
    """Widget displaying TARS-style status haiku."""

    DEFAULT_CSS = """
    HaikuDisplay {
        height: auto;
        padding: 1;
    }

    HaikuDisplay .haiku-line {
        text-align: center;
        color: $text;
    }

    HaikuDisplay .haiku-line-first {
        color: $primary-lighten;
    }
    """

    lines = reactive(["", "", ""])

    def compose(self) -> ComposeResult:
        for i, line in enumerate(self.lines):
            classes = "haiku-line"
            if i == 0:
                classes += " haiku-line-first"
            yield Static(line, classes=classes, id=f"haiku-{i}")

    def update_haiku(self, lines: list[str]) -> None:
        """Update the haiku text."""
        if len(lines) >= 3:
            self.lines = lines[:3]
            for i, line in enumerate(self.lines):
                try:
                    widget = self.query_one(f"#haiku-{i}", Static)
                    widget.update(line)
                except Exception:
                    pass


class ModeIndicator(Widget):
    """Widget showing current orchestrator mode."""

    DEFAULT_CSS = """
    ModeIndicator {
        height: 3;
        border: round $surface-lighter;
        padding: 0 1;
        content-align: center middle;
    }

    ModeIndicator.--interactive {
        border: round $success;
        color: $success;
    }

    ModeIndicator.--autonomous {
        border: round $warning;
        color: $warning;
    }

    ModeIndicator.--paused {
        border: round $text-dim;
        color: $text-dim;
    }
    """

    mode = reactive("interactive")

    MODE_LABELS = {
        "interactive": "INTERACTIVE",
        "autonomous": "AUTONOMOUS",
        "paused": "PAUSED",
    }

    def compose(self) -> ComposeResult:
        label = self.MODE_LABELS.get(self.mode, "UNKNOWN")
        yield Static(label, id="mode-label")

    def watch_mode(self, mode: str) -> None:
        """Update classes when mode changes."""
        self.remove_class("--interactive", "--autonomous", "--paused")
        self.add_class(f"--{mode}")

        try:
            label = self.query_one("#mode-label", Static)
            label.update(self.MODE_LABELS.get(mode, "UNKNOWN"))
        except Exception:
            pass

    def set_mode(self, mode: str) -> None:
        """Set the current mode."""
        self.mode = mode
