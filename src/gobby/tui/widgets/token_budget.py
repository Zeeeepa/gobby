"""Token budget meter widget."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import ProgressBar, Static


class TokenBudgetMeter(Widget):
    """Widget showing token budget usage with warning thresholds."""

    DEFAULT_CSS = """
    TokenBudgetMeter {
        height: auto;
        padding: 1;
    }

    TokenBudgetMeter .budget-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 1;
    }

    TokenBudgetMeter .budget-title {
        width: 1fr;
        color: #a6adc8;
    }

    TokenBudgetMeter .budget-percentage {
        width: auto;
        text-style: bold;
    }

    TokenBudgetMeter .budget-bar {
        height: 1;
        margin: 1 0;
    }

    TokenBudgetMeter .budget-details {
        layout: horizontal;
        height: 1;
    }

    TokenBudgetMeter .budget-spent {
        width: 1fr;
    }

    TokenBudgetMeter .budget-limit {
        width: auto;
        color: #a6adc8;
    }

    TokenBudgetMeter .--normal {
        color: #22c55e;
    }

    TokenBudgetMeter .--warning {
        color: #f59e0b;
    }

    TokenBudgetMeter .--critical {
        color: #ef4444;
    }
    """

    spent = reactive(0.0)
    limit = reactive(50.0)
    warning_threshold = reactive(0.8)
    critical_threshold = reactive(0.9)

    def compose(self) -> ComposeResult:
        percentage = self._get_percentage()

        with Horizontal(classes="budget-header"):
            yield Static("Token Budget", classes="budget-title")
            yield Static(
                f"{percentage:.0%}",
                classes=f"budget-percentage {self._get_status_class()}",
                id="percentage",
            )

        yield ProgressBar(
            total=100,
            progress=percentage * 100,
            show_eta=False,
            id="budget-bar",
            classes="budget-bar",
        )

        with Horizontal(classes="budget-details"):
            yield Static(
                f"${self.spent:.2f}",
                classes=f"budget-spent {self._get_status_class()}",
                id="spent",
            )
            yield Static(f"/ ${self.limit:.2f}", classes="budget-limit")

    def _get_percentage(self) -> float:
        """Get the current percentage used."""
        if self.limit <= 0:
            return 0.0
        return min(self.spent / self.limit, 1.0)

    def _get_status_class(self) -> str:
        """Get the CSS class based on usage level."""
        percentage = self._get_percentage()
        if percentage >= self.critical_threshold:
            return "--critical"
        elif percentage >= self.warning_threshold:
            return "--warning"
        return "--normal"

    def watch_spent(self, spent: float) -> None:
        """Update display when spent changes."""
        self._update_display()

    def watch_limit(self, limit: float) -> None:
        """Update display when limit changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update all display elements."""
        try:
            percentage = self._get_percentage()
            status_class = self._get_status_class()

            # Update percentage
            pct_widget = self.query_one("#percentage", Static)
            pct_widget.update(f"{percentage:.0%}")
            pct_widget.remove_class("--normal", "--warning", "--critical")
            pct_widget.add_class(status_class)

            # Update progress bar
            bar = self.query_one("#budget-bar", ProgressBar)
            bar.update(progress=percentage * 100)

            # Update spent
            spent_widget = self.query_one("#spent", Static)
            spent_widget.update(f"${self.spent:.2f}")
            spent_widget.remove_class("--normal", "--warning", "--critical")
            spent_widget.add_class(status_class)

        except Exception:
            pass

    def update_budget(self, spent: float, limit: float) -> None:
        """Update budget values."""
        self.spent = spent
        self.limit = limit

    def is_throttled(self) -> bool:
        """Check if usage is at throttle level."""
        return self._get_percentage() >= self.critical_threshold

    def is_warning(self) -> bool:
        """Check if usage is at warning level."""
        return self._get_percentage() >= self.warning_threshold
