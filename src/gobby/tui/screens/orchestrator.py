"""Orchestrator screen with conductor dashboard."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    LoadingIndicator,
    ProgressBar,
    Static,
)

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.ws_client import GobbyWebSocketClient


class ConductorPanel(Widget):
    """Panel displaying conductor haiku and status."""

    DEFAULT_CSS = """
    ConductorPanel {
        border: round #7c3aed;
        padding: 1 2;
        height: auto;
        min-height: 10;
    }

    ConductorPanel .conductor-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 1;
    }

    ConductorPanel .conductor-icon {
        width: 3;
    }

    ConductorPanel .conductor-title {
        text-style: bold;
        color: #a78bfa;
        width: 1fr;
    }

    ConductorPanel .haiku-container {
        padding: 1 2;
        margin: 1 0;
    }

    ConductorPanel .haiku-line {
        text-align: center;
        color: #cdd6f4;
    }
    """

    haiku_lines = reactive(["Ready to conduct", "Agents await your command", "Begin the journey"])

    def compose(self) -> ComposeResult:
        with Horizontal(classes="conductor-header"):
            yield Static("🎭", classes="conductor-icon")
            yield Static("Gobby Conductor", classes="conductor-title")

        with Vertical(classes="haiku-container"):
            for i, line in enumerate(self.haiku_lines):
                yield Static(line, classes="haiku-line", id=f"haiku-{i}")

    def update_haiku(self, lines: list[str]) -> None:
        """Update the haiku display."""
        self.haiku_lines = lines[:3] if len(lines) >= 3 else self.haiku_lines
        for i, line in enumerate(self.haiku_lines):
            try:
                widget = self.query_one(f"#haiku-{i}", Static)
                widget.update(line)
            except Exception:
                pass  # nosec B110 - widget may not be mounted yet


class TokenBudgetPanel(Widget):
    """Panel showing token budget and usage."""

    DEFAULT_CSS = """
    TokenBudgetPanel {
        border: round #45475a;
        padding: 1;
        height: auto;
    }

    TokenBudgetPanel .budget-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 1;
    }

    TokenBudgetPanel .budget-title {
        text-style: bold;
        color: #a78bfa;
        width: 1fr;
    }

    TokenBudgetPanel .budget-period {
        color: #6c7086;
    }

    TokenBudgetPanel .budget-bar-container {
        height: 2;
        margin: 1 0;
    }

    TokenBudgetPanel .budget-bar {
        height: 1;
    }

    TokenBudgetPanel .budget-details {
        layout: horizontal;
        height: 1;
    }

    TokenBudgetPanel .budget-spent {
        width: 1fr;
    }

    TokenBudgetPanel .budget-limit {
        width: auto;
        color: #a6adc8;
    }

    TokenBudgetPanel .budget-normal {
        color: #22c55e;
    }

    TokenBudgetPanel .budget-warning {
        color: #f59e0b;
    }

    TokenBudgetPanel .budget-critical {
        color: #ef4444;
    }
    """

    spent = reactive(0.0)
    limit = reactive(50.0)
    period = reactive("7d")

    def compose(self) -> ComposeResult:
        with Horizontal(classes="budget-header"):
            yield Static("💰 Token Budget", classes="budget-title")
            yield Static(f"({self.period})", classes="budget-period")

        with Vertical(classes="budget-bar-container"):
            yield ProgressBar(total=100, show_eta=False, id="budget-progress")

        with Horizontal(classes="budget-details"):
            yield Static(f"${self.spent:.2f}", classes="budget-spent", id="spent-value")
            yield Static(f"/ ${self.limit:.2f}", classes="budget-limit")

    def watch_spent(self, spent: float) -> None:
        """Update budget display when spent changes."""
        self._update_display()

    def watch_limit(self, limit: float) -> None:
        """Update budget display when limit changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the progress bar and values."""
        try:
            progress = self.query_one("#budget-progress", ProgressBar)
            spent_widget = self.query_one("#spent-value", Static)

            percentage = (self.spent / self.limit * 100) if self.limit > 0 else 0
            progress.update(progress=percentage)

            # Update colors based on usage
            spent_widget.update(f"${self.spent:.2f}")
            spent_widget.remove_class("budget-normal", "budget-warning", "budget-critical")

            if percentage >= 90:
                spent_widget.add_class("budget-critical")
            elif percentage >= 80:
                spent_widget.add_class("budget-warning")
            else:
                spent_widget.add_class("budget-normal")

        except Exception:
            pass  # nosec B110 - widget may not be mounted yet

    def update_budget(self, spent: float, limit: float, period: str = "7d") -> None:
        """Update budget values."""
        self.spent = spent
        self.limit = limit
        self.period = period


class ModeIndicatorPanel(Widget):
    """Panel showing and controlling conductor mode."""

    DEFAULT_CSS = """
    ModeIndicatorPanel {
        height: auto;
        padding: 1;
    }

    ModeIndicatorPanel .mode-header {
        text-style: bold;
        color: #a6adc8;
        margin-bottom: 1;
    }

    ModeIndicatorPanel .mode-button {
        width: 100%;
        height: 3;
    }

    ModeIndicatorPanel .mode-interactive {
        border: round #22c55e;
    }

    ModeIndicatorPanel .mode-autonomous {
        border: round #f59e0b;
    }

    ModeIndicatorPanel .mode-paused {
        border: round #6c7086;
    }

    ModeIndicatorPanel .mode-hint {
        color: #6c7086;
        margin-top: 1;
    }
    """

    mode = reactive("interactive")

    def compose(self) -> ComposeResult:
        yield Static("Mode:", classes="mode-header")

        mode_text = {
            "interactive": "INTERACTIVE",
            "autonomous": "AUTONOMOUS",
            "paused": "PAUSED",
        }.get(self.mode, "UNKNOWN")

        button_class = f"mode-{self.mode}"
        yield Button(mode_text, id="mode-toggle", classes=f"mode-button {button_class}")
        yield Static("[Space] to toggle", classes="mode-hint")

    def watch_mode(self, mode: str) -> None:
        """Update display when mode changes."""
        asyncio.create_task(self.recompose())

    def set_mode(self, mode: str) -> None:
        """Set the current mode."""
        self.mode = mode


class ActiveAgentsPanel(Widget):
    """Panel showing running agents."""

    DEFAULT_CSS = """
    ActiveAgentsPanel {
        border: round #45475a;
        padding: 1;
        height: 1fr;
    }

    ActiveAgentsPanel .panel-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 1;
    }

    ActiveAgentsPanel .panel-title {
        text-style: bold;
        color: #a78bfa;
        width: 1fr;
    }

    ActiveAgentsPanel .agent-count {
        color: #06b6d4;
    }

    ActiveAgentsPanel .agents-list {
        height: 1fr;
        overflow-y: auto;
    }

    ActiveAgentsPanel .agent-item {
        height: 2;
        padding: 0 1;
    }

    ActiveAgentsPanel .agent-status {
        color: #22c55e;
        width: 2;
    }

    ActiveAgentsPanel .agent-name {
        width: 1fr;
    }

    ActiveAgentsPanel .agent-duration {
        color: #6c7086;
        width: 6;
    }

    ActiveAgentsPanel .empty-state {
        color: #6c7086;
        content-align: center middle;
        height: 1fr;
    }
    """

    agents: reactive[list[dict[str, Any]]] = reactive(list)

    def compose(self) -> ComposeResult:
        running = [a for a in self.agents if a.get("status") == "running"]

        with Horizontal(classes="panel-header"):
            yield Static("🤖 Active Agents", classes="panel-title")
            yield Static(f"({len(running)})", classes="agent-count")

        if not running:
            yield Static("No agents running", classes="empty-state")
        else:
            with VerticalScroll(classes="agents-list"):
                for agent in running:
                    yield self._agent_item(agent)

    def _agent_item(self, agent: dict[str, Any]) -> Widget:
        """Create an agent item widget."""
        run_id = agent.get("run_id", "")[:8]
        branch = agent.get("branch", "")[:15] or "main"
        started = agent.get("started_at", "")

        # Calculate duration
        if started:
            try:
                started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                duration = datetime.now(started_dt.tzinfo) - started_dt
                total_minutes = int(duration.total_seconds() // 60)
                duration_str = f"{total_minutes}m"
            except Exception:
                duration_str = "?"
        else:
            duration_str = "?"

        return Static(f"● {run_id} ({branch}) {duration_str}", classes="agent-item")

    def watch_agents(self, agents: list[dict[str, Any]]) -> None:
        """Recompose when agents change."""
        asyncio.create_task(self.recompose())

    def update_agents(self, agents: list[dict[str, Any]]) -> None:
        """Update the agents list."""
        self.agents = agents


class ReviewQueuePanel(Widget):
    """Panel showing tasks in review status."""

    DEFAULT_CSS = """
    ReviewQueuePanel {
        border: round #45475a;
        padding: 1;
        height: 1fr;
    }

    ReviewQueuePanel .panel-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 1;
    }

    ReviewQueuePanel .panel-title {
        text-style: bold;
        color: #a78bfa;
        width: 1fr;
    }

    ReviewQueuePanel .queue-count {
        color: #a855f7;
    }

    ReviewQueuePanel .review-list {
        height: 1fr;
        overflow-y: auto;
    }

    ReviewQueuePanel .review-item {
        height: 2;
        padding: 0 1;
    }

    ReviewQueuePanel .review-item:hover {
        background: #45475a;
    }

    ReviewQueuePanel .review-item.--selected {
        background: #6d28d9;
    }

    ReviewQueuePanel .review-id {
        color: #a855f7;
        width: 16;
    }

    ReviewQueuePanel .review-title {
        width: 1fr;
    }

    ReviewQueuePanel .review-time {
        color: #6c7086;
        width: 6;
    }

    ReviewQueuePanel .action-row {
        layout: horizontal;
        height: 3;
        margin-top: 1;
    }

    ReviewQueuePanel .action-row Button {
        margin-right: 1;
    }

    ReviewQueuePanel .empty-state {
        color: #6c7086;
        content-align: center middle;
        height: 1fr;
    }
    """

    tasks: reactive[list[dict[str, Any]]] = reactive(list)
    selected_index = reactive(0)

    def compose(self) -> ComposeResult:
        review_tasks = [t for t in self.tasks if t.get("status") == "review"]

        with Horizontal(classes="panel-header"):
            yield Static("📋 Review Queue", classes="panel-title")
            yield Static(f"({len(review_tasks)})", classes="queue-count")

        if not review_tasks:
            yield Static("No tasks awaiting review", classes="empty-state")
        else:
            with VerticalScroll(classes="review-list"):
                for i, task in enumerate(review_tasks):
                    ref = task.get("ref", "")
                    title = task.get("title", "Untitled")[:25]
                    if len(task.get("title", "")) > 25:
                        title += "..."

                    # Calculate wait time
                    updated = task.get("updated_at", "")
                    if updated:
                        try:
                            updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                            wait = datetime.now(updated_dt.tzinfo) - updated_dt
                            minutes = int(wait.total_seconds() // 60)
                            wait_str = f"⏳{minutes}m"
                        except Exception:
                            wait_str = "⏳?"
                    else:
                        wait_str = "⏳?"

                    classes = "review-item"
                    if i == self.selected_index:
                        classes += " --selected"

                    yield Static(f"{ref} {title} {wait_str}", classes=classes, id=f"review-{i}")

            with Horizontal(classes="action-row"):
                yield Button("[Y] Approve", variant="success", id="btn-approve")
                yield Button("[N] Reject", variant="error", id="btn-reject")

    def watch_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Recompose when tasks change."""
        asyncio.create_task(self.recompose())

    def update_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Update the tasks list."""
        self.tasks = tasks

    def get_selected_task(self) -> dict[str, Any] | None:
        """Get the currently selected task."""
        review_tasks = [t for t in self.tasks if t.get("status") == "review"]
        if 0 <= self.selected_index < len(review_tasks):
            return review_tasks[self.selected_index]
        return None


class InterAgentMessagePanel(Widget):
    """Panel showing inter-agent messages."""

    DEFAULT_CSS = """
    InterAgentMessagePanel {
        border: round #45475a;
        padding: 1;
        height: 1fr;
    }

    InterAgentMessagePanel .panel-title {
        text-style: bold;
        color: #a78bfa;
        margin-bottom: 1;
    }

    InterAgentMessagePanel .messages-list {
        height: 1fr;
        overflow-y: auto;
    }

    InterAgentMessagePanel .message-item {
        height: 1;
        padding: 0 1;
    }

    InterAgentMessagePanel .message-outgoing {
        color: #06b6d4;
    }

    InterAgentMessagePanel .message-incoming {
        color: #cdd6f4;
    }

    InterAgentMessagePanel .message-sender {
        color: #a6adc8;
    }

    InterAgentMessagePanel .empty-state {
        color: #6c7086;
        content-align: center middle;
        height: 1fr;
    }
    """

    messages: reactive[list[dict[str, Any]]] = reactive(list)

    def compose(self) -> ComposeResult:
        yield Static("💬 Inter-Agent Messages", classes="panel-title")

        if not self.messages:
            yield Static("No messages yet", classes="empty-state")
        else:
            with VerticalScroll(classes="messages-list"):
                for msg in self.messages[-20:]:  # Show last 20
                    direction = msg.get("direction", "outgoing")
                    sender = msg.get("sender", "unknown")[:8]
                    content = msg.get("content", "")[:60]

                    arrow = "→" if direction == "outgoing" else "←"
                    css_class = f"message-{direction}"

                    yield Static(
                        f"{arrow} [{sender}] {content}", classes=f"message-item {css_class}"
                    )

    def watch_messages(self, messages: list[dict[str, Any]]) -> None:
        """Recompose when messages change."""
        asyncio.create_task(self.recompose())

    def add_message(self, sender: str, content: str, direction: str = "incoming") -> None:
        """Add a new message."""
        new_messages = list(self.messages)
        new_messages.append(
            {
                "sender": sender,
                "content": content,
                "direction": direction,
                "timestamp": datetime.now().isoformat(),
            }
        )
        # Keep last 100 messages
        self.messages = new_messages[-100:]


class OrchestratorScreen(Widget):
    """Orchestrator screen with conductor dashboard."""

    DEFAULT_CSS = """
    OrchestratorScreen {
        width: 1fr;
        height: 1fr;
    }

    OrchestratorScreen #orchestrator-grid {
        layout: grid;
        grid-size: 2 3;
        grid-gutter: 1;
        padding: 1;
        height: 1fr;
    }

    OrchestratorScreen #conductor-panel {
        row-span: 1;
        column-span: 1;
    }

    OrchestratorScreen #budget-mode-container {
        row-span: 1;
        column-span: 1;
    }

    OrchestratorScreen #active-agents-panel {
        row-span: 1;
        column-span: 1;
    }

    OrchestratorScreen #review-queue-panel {
        row-span: 1;
        column-span: 1;
    }

    OrchestratorScreen #messages-panel {
        row-span: 1;
        column-span: 2;
    }

    OrchestratorScreen .loading-container {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    loading = reactive(True)
    mode = reactive("interactive")

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
        if self.loading:
            with Container(classes="loading-container"):
                yield LoadingIndicator()
        else:
            with Grid(id="orchestrator-grid"):
                yield ConductorPanel(id="conductor-panel")

                with Vertical(id="budget-mode-container"):
                    yield TokenBudgetPanel(id="budget-panel")
                    yield ModeIndicatorPanel(id="mode-panel")

                yield ActiveAgentsPanel(id="active-agents-panel")
                yield ReviewQueuePanel(id="review-queue-panel")
                yield InterAgentMessagePanel(id="messages-panel")

    async def on_mount(self) -> None:
        """Load data when mounted."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh orchestrator data."""
        try:
            status = await self.api_client.get_status()
            tasks = await self.api_client.list_tasks(status="review")
            agents = await self.api_client.list_agents()
            await self._update_panels(status, tasks, agents)

        except Exception as e:
            self.notify(f"Failed to load orchestrator data: {e}", severity="error")
        finally:
            self.loading = False
            await self.recompose()

    async def _update_panels(
        self,
        status: dict[str, Any],
        tasks: list[dict[str, Any]],
        agents: list[dict[str, Any]],
    ) -> None:
        """Update all orchestrator panels."""
        try:
            # Update conductor haiku based on status
            conductor = self.query_one("#conductor-panel", ConductorPanel)
            haiku = self._generate_conductor_haiku(status, tasks, agents)
            conductor.update_haiku(haiku)

            # Update budget (placeholder values for now)
            budget = self.query_one("#budget-panel", TokenBudgetPanel)
            budget.update_budget(spent=33.50, limit=50.00, period="7d")

            # Update mode
            mode_panel = self.query_one("#mode-panel", ModeIndicatorPanel)
            mode_panel.set_mode(self.mode)

            # Update agents
            agents_panel = self.query_one("#active-agents-panel", ActiveAgentsPanel)
            agents_panel.update_agents(agents)

            # Update review queue
            review_panel = self.query_one("#review-queue-panel", ReviewQueuePanel)
            review_panel.update_tasks(tasks)

        except Exception:
            pass  # nosec B110 - TUI update failure is non-critical

    def _generate_conductor_haiku(
        self,
        status: dict[str, Any],
        tasks: list[dict[str, Any]],
        agents: list[dict[str, Any]],
    ) -> list[str]:
        """Generate a haiku based on current state."""
        review_count = len([t for t in tasks if t.get("status") == "review"])
        running_agents = len([a for a in agents if a.get("status") == "running"])
        tasks_info = status.get("tasks", {})
        open_count = tasks_info.get("open", 0)

        if review_count > 0:
            return [
                f"{review_count} await review",
                "Code written, tests complete",
                "Your approval waits",
            ]
        elif running_agents > 0:
            return [
                f"{running_agents} agent{'s' if running_agents != 1 else ''} at work",
                "Code flows through busy hands",
                "Progress unfolds",
            ]
        elif open_count > 0:
            return [
                f"{open_count} tasks await you",
                "Ready for your attention",
                "Choose and begin",
            ]
        else:
            return [
                "All is quiet now",
                "No tasks need attention here",
                "Peace in the system",
            ]

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "mode-toggle":
            await self._toggle_mode()

        elif button_id == "btn-approve":
            await self._approve_task()

        elif button_id == "btn-reject":
            await self._reject_task()

    async def on_key(self, event: Any) -> None:
        """Handle key events for orchestrator shortcuts."""
        key = event.key

        if key == "space":
            await self._toggle_mode()
        elif key == "y":
            await self._approve_task()
        elif key == "n":
            await self._reject_task()
        elif key == "p":
            self.mode = "paused"
            await self._update_mode_panel()
        elif key in ("j", "down"):
            await self._navigate_review_queue(1)
        elif key in ("k", "up"):
            await self._navigate_review_queue(-1)

    async def _navigate_review_queue(self, delta: int) -> None:
        """Navigate review queue selection."""
        try:
            review_panel = self.query_one("#review-queue-panel", ReviewQueuePanel)
            review_tasks = [t for t in review_panel.tasks if t.get("status") == "review"]
            if not review_tasks:
                return
            new_index = review_panel.selected_index + delta
            review_panel.selected_index = max(0, min(new_index, len(review_tasks) - 1))
        except Exception:
            pass  # nosec B110 - navigation failure is non-critical

    async def _toggle_mode(self) -> None:
        """Toggle between interactive and autonomous modes."""
        if self.mode == "interactive":
            self.mode = "autonomous"
            self.notify("Autonomous mode enabled")
        elif self.mode == "autonomous":
            self.mode = "interactive"
            self.notify("Interactive mode enabled")
        else:
            self.mode = "interactive"
            self.notify("Resumed to interactive mode")

        await self._update_mode_panel()

    async def _update_mode_panel(self) -> None:
        """Update the mode panel display."""
        try:
            mode_panel = self.query_one("#mode-panel", ModeIndicatorPanel)
            mode_panel.set_mode(self.mode)
        except Exception:
            pass  # nosec B110 - widget may not be mounted yet

    async def _approve_task(self) -> None:
        """Approve the selected review task."""
        try:
            review_panel = self.query_one("#review-queue-panel", ReviewQueuePanel)
            task = review_panel.get_selected_task()

            if not task:
                self.notify("No task selected", severity="warning")
                return

            task_id = task.get("id")
            if task_id is None:
                self.notify("Task has no ID", severity="error")
                return
            await self.api_client.close_task(
                task_id,
                no_commit_needed=True,
                override_justification="Orchestrator approval - manual user review",
            )
            self.notify(f"Approved: {task.get('ref', task_id)}")

            messages_panel = self.query_one("#messages-panel", InterAgentMessagePanel)
            messages_panel.add_message(
                "conductor", f"Approved task {task.get('ref', '')}", "outgoing"
            )

            await self.refresh_data()

        except Exception as e:
            self.notify(f"Failed to approve: {e}", severity="error")

    async def _reject_task(self) -> None:
        """Reject/reopen the selected review task."""
        try:
            review_panel = self.query_one("#review-queue-panel", ReviewQueuePanel)
            task = review_panel.get_selected_task()

            if not task:
                self.notify("No task selected", severity="warning")
                return

            task_id = task.get("id")
            await self.api_client.call_tool(
                "gobby-tasks",
                "reopen_task",
                {"task_id": task_id},
            )
            self.notify(f"Rejected: {task.get('ref', task_id)}")

            messages_panel = self.query_one("#messages-panel", InterAgentMessagePanel)
            messages_panel.add_message(
                "conductor", f"Rejected task {task.get('ref', '')}", "outgoing"
            )

            await self.refresh_data()

        except Exception as e:
            self.notify(f"Failed to reject: {e}", severity="error")

    def on_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle WebSocket events."""
        try:
            # Handle agent events
            if event_type == "agent_event":
                event = data.get("event", "")
                run_id = data.get("run_id", "")[:8]

                messages_panel = self.query_one("#messages-panel", InterAgentMessagePanel)
                messages_panel.add_message(run_id, f"Agent {event}", "incoming")

                asyncio.create_task(self.refresh_data())

            # Handle autonomous events
            elif event_type == "autonomous_event":
                event = data.get("event", "")
                task_id = data.get("task_id", "")

                messages_panel = self.query_one("#messages-panel", InterAgentMessagePanel)
                messages_panel.add_message("system", f"{event}: {task_id}", "incoming")

                asyncio.create_task(self.refresh_data())

            # Handle session messages (inter-agent)
            elif event_type == "session_message":
                session_id = data.get("session_id", "")[:8]
                content = data.get("message", {}).get("content", "")[:60]

                messages_panel = self.query_one("#messages-panel", InterAgentMessagePanel)
                messages_panel.add_message(session_id, content, "incoming")

        except Exception:
            pass  # nosec B110 - TUI event handling failure is non-critical
