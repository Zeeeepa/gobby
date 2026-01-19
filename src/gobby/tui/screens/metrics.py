"""Metrics screen with tool usage statistics."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    LoadingIndicator,
    Static,
)

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.ws_client import GobbyWebSocketClient


class MetricsSummaryPanel(Widget):
    """Panel showing metrics summary."""

    DEFAULT_CSS = """
    MetricsSummaryPanel {
        height: auto;
        padding: 1;
        border: round #45475a;
        margin: 1;
    }

    MetricsSummaryPanel .summary-title {
        text-style: bold;
        color: #a78bfa;
        padding-bottom: 1;
    }

    MetricsSummaryPanel .summary-grid {
        layout: grid;
        grid-size: 4 1;
        grid-gutter: 2;
    }

    MetricsSummaryPanel .stat-box {
        height: 4;
        border: round #45475a;
        padding: 0 1;
        content-align: center middle;
    }

    MetricsSummaryPanel .stat-value {
        text-style: bold;
        color: #06b6d4;
    }

    MetricsSummaryPanel .stat-label {
        color: #a6adc8;
    }
    """

    metrics: reactive[dict[str, Any] | None] = reactive(None)

    def compose(self) -> ComposeResult:
        yield Static("📊 Summary", classes="summary-title")

        with Horizontal(classes="summary-grid"):
            # Total calls
            with Vertical(classes="stat-box"):
                total = self.metrics.get("total_calls", 0) if self.metrics else 0
                yield Static(str(total), classes="stat-value")
                yield Static("Total Calls", classes="stat-label")

            # Success rate
            with Vertical(classes="stat-box"):
                rate = self.metrics.get("success_rate", 0) if self.metrics else 0
                yield Static(f"{rate:.1%}", classes="stat-value")
                yield Static("Success Rate", classes="stat-label")

            # Avg response time
            with Vertical(classes="stat-box"):
                avg_time = self.metrics.get("avg_response_ms", 0) if self.metrics else 0
                yield Static(f"{avg_time:.0f}ms", classes="stat-value")
                yield Static("Avg Response", classes="stat-label")

            # Active servers
            with Vertical(classes="stat-box"):
                servers = self.metrics.get("active_servers", 0) if self.metrics else 0
                yield Static(str(servers), classes="stat-value")
                yield Static("Active Servers", classes="stat-label")

    def watch_metrics(self, metrics: dict[str, Any] | None) -> None:
        """Recompose when metrics change."""
        asyncio.create_task(self.recompose())


class MetricsScreen(Widget):
    """Metrics screen showing tool usage statistics."""

    DEFAULT_CSS = """
    MetricsScreen {
        width: 1fr;
        height: 1fr;
    }

    MetricsScreen .screen-header {
        height: auto;
        padding: 1;
        background: #313244;
    }

    MetricsScreen .header-row {
        layout: horizontal;
    }

    MetricsScreen .panel-title {
        text-style: bold;
        color: #a78bfa;
        width: 1fr;
    }

    MetricsScreen .content-area {
        height: 1fr;
        padding: 1;
    }

    MetricsScreen #tools-table {
        height: 1fr;
    }

    MetricsScreen .loading-container {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    loading = reactive(True)
    metrics: reactive[dict[str, Any] | None] = reactive(None)
    tool_metrics: reactive[list[dict[str, Any]]] = reactive(list)

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
        with Vertical(classes="screen-header"):
            with Horizontal(classes="header-row"):
                yield Static("📈 Metrics", classes="panel-title")
                yield Button("Refresh", id="btn-refresh")
                yield Button("Export", id="btn-export")

        if self.loading:
            with Container(classes="loading-container"):
                yield LoadingIndicator()
        else:
            with Vertical(classes="content-area"):
                yield MetricsSummaryPanel(id="summary-panel")
                yield Static("Tool Usage", classes="panel-title")
                yield DataTable(id="tools-table")

    async def on_mount(self) -> None:
        """Load data when mounted."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh metrics data."""
        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                result = await client.call_tool(
                    "gobby-metrics",
                    "get_metrics",
                    {},
                )
                self.metrics = result.get("summary", {})
                self.tool_metrics = result.get("tools", [])

        except Exception as e:
            self.notify(f"Failed to load metrics: {e}", severity="error")
        finally:
            self.loading = False
            await self.recompose()
            await self._update_summary()
            await self._setup_table()

    async def _update_summary(self) -> None:
        """Update the summary panel."""
        try:
            panel = self.query_one("#summary-panel", MetricsSummaryPanel)
            panel.metrics = self.metrics
        except NoMatches:
            pass  # Widget may not be mounted yet

    async def _setup_table(self) -> None:
        """Set up and populate the tools table."""
        try:
            table = self.query_one("#tools-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Server", "Tool", "Calls", "Success", "Avg Time")
            table.cursor_type = "row"

            for tool in self.tool_metrics:
                server = tool.get("server", "unknown")
                name = tool.get("name", "unknown")
                calls = str(tool.get("calls", 0))
                success = f"{tool.get('success_rate', 0):.1%}"
                avg_time = f"{tool.get('avg_ms', 0):.0f}ms"

                table.add_row(server, name, calls, success, avg_time)

        except NoMatches:
            pass  # Table widget may not be mounted yet

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-refresh":
            self.loading = True
            await self.refresh_data()

        elif button_id == "btn-export":
            self.notify("Export coming soon", severity="information")
