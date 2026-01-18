"""Dashboard screen with overview widgets."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Grid, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import LoadingIndicator, Static

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.ws_client import GobbyWebSocketClient


class HaikuPanel(Static):
    """Panel displaying TARS-style haiku status."""

    DEFAULT_CSS = """
    HaikuPanel {
        border: round #7c3aed;
        padding: 1 2;
        height: auto;
        min-height: 8;
    }

    HaikuPanel .haiku-title {
        text-style: bold;
        color: #a78bfa;
        text-align: center;
        padding-bottom: 1;
    }

    HaikuPanel .haiku-line {
        text-align: center;
        color: #cdd6f4;
        padding: 0 1;
    }
    """

    haiku_lines = reactive(["Tasks await your hands", "Agents stand ready to serve", "Begin your journey"])

    def compose(self) -> ComposeResult:
        yield Static("🎭 Gobby", classes="haiku-title")
        for i, line in enumerate(self.haiku_lines):
            yield Static(line, classes="haiku-line", id=f"haiku-line-{i}")

    def watch_haiku_lines(self, lines: list[str]) -> None:
        for i, line in enumerate(lines[:3]):
            try:
                widget = self.query_one(f"#haiku-line-{i}", Static)
                widget.update(line)
            except Exception:
                pass

    def update_haiku(self, lines: list[str]) -> None:
        """Update the haiku display."""
        self.haiku_lines = lines[:3] if lines else self.haiku_lines


class StatsPanel(Static):
    """Panel displaying system statistics."""

    DEFAULT_CSS = """
    StatsPanel {
        border: round #45475a;
        padding: 1 2;
        height: auto;
    }

    StatsPanel .panel-title {
        text-style: bold;
        color: #a78bfa;
        padding-bottom: 1;
    }

    StatsPanel .stat-row {
        layout: horizontal;
        height: 1;
    }

    StatsPanel .stat-label {
        width: 1fr;
        color: #a6adc8;
    }

    StatsPanel .stat-value {
        width: auto;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("📊 Statistics", classes="panel-title")
        stats = [
            ("Tasks Open", "tasks-open", "0"),
            ("Tasks In Progress", "tasks-progress", "0"),
            ("Active Sessions", "sessions-active", "0"),
            ("Running Agents", "agents-running", "0"),
            ("MCP Servers", "mcp-servers", "0"),
            ("Memory Items", "memory-items", "0"),
        ]
        for label, stat_id, default in stats:
            with Container(classes="stat-row"):
                yield Static(label, classes="stat-label")
                yield Static(default, classes="stat-value", id=f"stat-{stat_id}")

    def update_stat(self, stat_id: str, value: str | int) -> None:
        """Update a specific stat value."""
        try:
            widget = self.query_one(f"#stat-{stat_id}", Static)
            widget.update(str(value))
        except Exception:
            pass


class ActivityPanel(Static):
    """Panel displaying recent activity."""

    DEFAULT_CSS = """
    ActivityPanel {
        border: round #45475a;
        padding: 1 2;
        height: 1fr;
        min-height: 10;
    }

    ActivityPanel .panel-title {
        text-style: bold;
        color: #a78bfa;
        padding-bottom: 1;
    }

    ActivityPanel .activity-list {
        height: 1fr;
        overflow-y: auto;
    }

    ActivityPanel .activity-item {
        height: 1;
        color: #a6adc8;
    }

    ActivityPanel .activity-time {
        color: #6c7086;
        width: 10;
    }

    ActivityPanel .activity-event {
        width: 1fr;
    }
    """

    activities: reactive[list[dict[str, Any]]] = reactive(list)

    def compose(self) -> ComposeResult:
        yield Static("📜 Recent Activity", classes="panel-title")
        yield Vertical(id="activity-list", classes="activity-list")

    def watch_activities(self, activities: list[dict[str, Any]]) -> None:
        self._refresh_activities()

    def _refresh_activities(self) -> None:
        """Refresh the activity list display."""
        try:
            container = self.query_one("#activity-list", Vertical)
            container.remove_children()
            for activity in self.activities[-10:]:  # Show last 10
                time_str = activity.get("time", "")[:8]
                event = activity.get("event", "Unknown event")
                container.mount(
                    Static(f"[{time_str}] {event}", classes="activity-item")
                )
        except Exception:
            pass

    def add_activity(self, event: str, time_str: str | None = None) -> None:
        """Add a new activity to the list."""
        from datetime import datetime

        if time_str is None:
            time_str = datetime.now().strftime("%H:%M:%S")
        new_activities = list(self.activities)
        new_activities.append({"time": time_str, "event": event})
        # Keep last 50 activities
        self.activities = new_activities[-50:]


class DashboardScreen(Widget):
    """Dashboard screen showing overview of Gobby status."""

    DEFAULT_CSS = """
    DashboardScreen {
        width: 1fr;
        height: 1fr;
    }

    DashboardScreen #dashboard-grid {
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 1;
        padding: 1;
        height: 1fr;
    }

    DashboardScreen #haiku-panel {
        column-span: 1;
        row-span: 1;
    }

    DashboardScreen #stats-panel {
        column-span: 1;
        row-span: 1;
    }

    DashboardScreen #activity-panel {
        column-span: 2;
        row-span: 1;
    }

    DashboardScreen .loading-container {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    loading = reactive(True)

    def __init__(
        self,
        api_client: GobbyAPIClient,
        ws_client: GobbyWebSocketClient,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_client = api_client
        self.ws_client = ws_client

    def compose(self) -> ComposeResult:
        if self.loading:
            with Container(classes="loading-container"):
                yield LoadingIndicator()
        else:
            with Grid(id="dashboard-grid"):
                yield HaikuPanel(id="haiku-panel")
                yield StatsPanel(id="stats-panel")
                yield ActivityPanel(id="activity-panel")

    async def on_mount(self) -> None:
        """Load data when mounted."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh all dashboard data."""
        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                # Fetch all data first before any UI updates
                status = await client.get_status()
                agents = await client.list_agents()

            # Now update UI - set loading to false and recompose if needed
            if self.loading:
                self.loading = False
                await self.recompose()

            # Update stats panel
            stats_panel = self.query_one("#stats-panel", StatsPanel)

            # Task counts
            tasks_summary = status.get("tasks", {})
            stats_panel.update_stat("tasks-open", tasks_summary.get("open", 0))
            stats_panel.update_stat("tasks-progress", tasks_summary.get("in_progress", 0))

            # Session count
            sessions_summary = status.get("sessions", {})
            stats_panel.update_stat("sessions-active", sessions_summary.get("active", 0))

            # Agent count
            running_agents = len([a for a in agents if a.get("status") == "running"])
            stats_panel.update_stat("agents-running", running_agents)

            # MCP servers
            mcp_status = status.get("mcp_servers", {})
            stats_panel.update_stat("mcp-servers", mcp_status.get("connected", 0))

            # Memory count
            memory_status = status.get("memory", {})
            stats_panel.update_stat("memory-items", memory_status.get("count", 0))

            # Update haiku based on status
            haiku_panel = self.query_one("#haiku-panel", HaikuPanel)
            haiku = self._generate_status_haiku(status)
            haiku_panel.update_haiku(haiku)

            # Add initial activity
            activity_panel = self.query_one("#activity-panel", ActivityPanel)
            activity_panel.add_activity("Dashboard loaded")

        except Exception as e:
            # Show error state
            self.loading = False
            self.notify(f"Failed to load dashboard: {e}", severity="error")

    def _generate_status_haiku(self, status: dict[str, Any]) -> list[str]:
        """Generate a haiku based on system status."""
        tasks = status.get("tasks", {})
        open_count = tasks.get("open", 0)
        in_progress = tasks.get("in_progress", 0)

        if open_count == 0 and in_progress == 0:
            return [
                "All tasks complete",
                "The queue stands empty now",
                "Peace in the system",
            ]
        elif in_progress > 0:
            return [
                f"{in_progress} task{'s' if in_progress != 1 else ''} in flight",
                "Code flows through eager hands",
                "Progress unfolds",
            ]
        else:
            return [
                f"{open_count} await your call",
                "Ready to begin the work",
                "Choose your first task",
            ]

    def on_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle WebSocket events."""
        # Add to activity feed
        try:
            activity_panel = self.query_one("#activity-panel", ActivityPanel)

            if event_type == "agent_event":
                event = data.get("event", "")
                run_id = data.get("run_id", "")[:8]
                activity_panel.add_activity(f"Agent {run_id}: {event}")

            elif event_type == "hook_event":
                hook_type = data.get("event_type", "")
                activity_panel.add_activity(f"Hook: {hook_type}")

            elif event_type == "worktree_event":
                event = data.get("event", "")
                branch = data.get("branch_name", "")
                activity_panel.add_activity(f"Worktree {branch}: {event}")

            elif event_type == "autonomous_event":
                event = data.get("event", "")
                task_id = data.get("task_id", "")
                activity_panel.add_activity(f"Auto: {event} ({task_id})")

        except Exception:
            pass

        # Refresh stats periodically on events
        asyncio.create_task(self._refresh_stats_quietly())

    async def _refresh_stats_quietly(self) -> None:
        """Refresh stats without full reload."""
        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                status = await client.get_status()
                stats_panel = self.query_one("#stats-panel", StatsPanel)

                tasks_summary = status.get("tasks", {})
                stats_panel.update_stat("tasks-open", tasks_summary.get("open", 0))
                stats_panel.update_stat("tasks-progress", tasks_summary.get("in_progress", 0))

                sessions_summary = status.get("sessions", {})
                stats_panel.update_stat("sessions-active", sessions_summary.get("active", 0))
        except Exception:
            pass
