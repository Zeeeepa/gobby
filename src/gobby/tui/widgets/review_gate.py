"""Review gate panel widget."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Static


class ReviewItem(Static):
    """A single review queue item."""

    DEFAULT_CSS = """
    ReviewItem {
        height: 2;
        padding: 0 1;
    }

    ReviewItem:hover {
        background: $surface-lighter;
    }

    ReviewItem.--selected {
        background: $primary-darken;
    }

    ReviewItem .review-content {
        layout: horizontal;
    }

    ReviewItem .review-ref {
        color: $status-review;
        width: 12;
    }

    ReviewItem .review-title {
        width: 1fr;
    }

    ReviewItem .review-wait {
        color: $text-dim;
        width: 8;
    }
    """

    selected = reactive(False)

    def __init__(self, task: dict[str, Any], **kwargs) -> None:
        super().__init__(**kwargs)
        self.task = task

    def compose(self) -> ComposeResult:
        ref = self.task.get("ref", "")
        title = self.task.get("title", "Untitled")[:30]
        if len(self.task.get("title", "")) > 30:
            title += "..."

        # Calculate wait time
        updated = self.task.get("updated_at", "")
        if updated:
            try:
                updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                wait = datetime.now(updated_dt.tzinfo) - updated_dt
                wait_str = f"⏳{wait.seconds // 60}m"
            except Exception:
                wait_str = "⏳?"
        else:
            wait_str = "⏳?"

        with Horizontal(classes="review-content"):
            yield Static(ref, classes="review-ref")
            yield Static(title, classes="review-title")
            yield Static(wait_str, classes="review-wait")

    def watch_selected(self, selected: bool) -> None:
        """Update selected class."""
        self.set_class(selected, "--selected")

    def on_click(self) -> None:
        """Handle click to select."""
        self.post_message(ReviewGatePanel.ItemSelected(self.task))


class ReviewGatePanel(Widget):
    """Panel showing tasks awaiting review with approve/reject actions."""

    DEFAULT_CSS = """
    ReviewGatePanel {
        height: 1fr;
        border: round $surface-lighter;
    }

    ReviewGatePanel .panel-header {
        layout: horizontal;
        height: 1;
        padding: 0 1;
        background: $surface-light;
    }

    ReviewGatePanel .panel-title {
        text-style: bold;
        color: $primary-lighten;
        width: 1fr;
    }

    ReviewGatePanel .queue-count {
        color: $status-review;
    }

    ReviewGatePanel .review-list {
        height: 1fr;
        padding: 1;
    }

    ReviewGatePanel .action-row {
        layout: horizontal;
        height: 3;
        padding: 1;
        border-top: solid $surface-lighter;
    }

    ReviewGatePanel .action-row Button {
        margin-right: 1;
    }

    ReviewGatePanel .empty-state {
        content-align: center middle;
        height: 1fr;
        color: $text-dim;
    }
    """

    tasks: reactive[list[dict[str, Any]]] = reactive(list)
    selected_task: reactive[dict[str, Any] | None] = reactive(None)

    @dataclass
    class ItemSelected(Message):
        """Message sent when a review item is selected."""
        task: dict[str, Any]

    @dataclass
    class TaskApproved(Message):
        """Message sent when a task is approved."""
        task: dict[str, Any]

    @dataclass
    class TaskRejected(Message):
        """Message sent when a task is rejected."""
        task: dict[str, Any]

    def compose(self) -> ComposeResult:
        review_tasks = [t for t in self.tasks if t.get("status") == "review"]

        with Horizontal(classes="panel-header"):
            yield Static("📋 Review Queue", classes="panel-title")
            yield Static(f"({len(review_tasks)})", classes="queue-count")

        if not review_tasks:
            yield Static("No tasks awaiting review", classes="empty-state")
        else:
            with VerticalScroll(classes="review-list"):
                for task in review_tasks:
                    item = ReviewItem(task, id=f"review-{task.get('id', '')}")
                    if self.selected_task and task.get("id") == self.selected_task.get("id"):
                        item.selected = True
                    yield item

            with Horizontal(classes="action-row"):
                yield Button("Approve", variant="success", id="btn-approve")
                yield Button("Reject", variant="error", id="btn-reject")

    def on_review_gate_panel_item_selected(self, event: ItemSelected) -> None:
        """Handle item selection."""
        self.selected_task = event.task
        self._update_selection()

    def _update_selection(self) -> None:
        """Update selected state of all items."""
        for task in self.tasks:
            try:
                item = self.query_one(f"#review-{task.get('id', '')}", ReviewItem)
                item.selected = (
                    self.selected_task is not None
                    and task.get("id") == self.selected_task.get("id")
                )
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle action button presses."""
        if not self.selected_task:
            return

        if event.button.id == "btn-approve":
            self.post_message(self.TaskApproved(self.selected_task))
        elif event.button.id == "btn-reject":
            self.post_message(self.TaskRejected(self.selected_task))

    def update_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Update the tasks list."""
        self.tasks = tasks

    def get_selected_task(self) -> dict[str, Any] | None:
        """Get the currently selected task."""
        return self.selected_task
