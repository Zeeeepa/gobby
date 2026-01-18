"""Worktrees screen with git worktree management."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
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


class WorktreesScreen(Widget):
    """Worktrees screen showing git worktree status."""

    DEFAULT_CSS = """
    WorktreesScreen {
        width: 1fr;
        height: 1fr;
    }

    WorktreesScreen .screen-header {
        height: auto;
        padding: 1;
        background: #313244;
    }

    WorktreesScreen .header-row {
        layout: horizontal;
    }

    WorktreesScreen .panel-title {
        text-style: bold;
        color: #a78bfa;
        width: 1fr;
    }

    WorktreesScreen #worktrees-table {
        height: 1fr;
    }

    WorktreesScreen .loading-container {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }

    WorktreesScreen .empty-state {
        content-align: center middle;
        height: 1fr;
        color: #a6adc8;
    }
    """

    loading = reactive(True)
    worktrees: reactive[list[dict[str, Any]]] = reactive(list)
    selected_worktree_id: reactive[str | None] = reactive(None)

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
                yield Static("🌳 Worktrees", classes="panel-title")
                yield Button("+ Create", variant="primary", id="btn-create")
                yield Button("Cleanup", id="btn-cleanup")
                yield Button("Refresh", id="btn-refresh")

        if self.loading:
            with Container(classes="loading-container"):
                yield LoadingIndicator()
        elif not self.worktrees:
            yield Static(
                "No worktrees found. Create one to enable parallel development.",
                classes="empty-state",
            )
        else:
            yield DataTable(id="worktrees-table")

    async def on_mount(self) -> None:
        """Load data when mounted."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh worktree list."""
        try:
            worktrees = await self.api_client.list_worktrees()
            self.worktrees = worktrees
        except Exception as e:
            self.notify(f"Failed to load worktrees: {e}", severity="error")
        finally:
            self.loading = False
            await self.recompose()
            await self._setup_table()

    async def _setup_table(self) -> None:
        """Set up and populate the worktrees table."""
        if not self.worktrees:
            return

        try:
            table = self.query_one("#worktrees-table", DataTable)
            table.clear(columns=True)
            table.add_columns("ID", "Branch", "Status", "Task", "Path")
            table.cursor_type = "row"

            for wt in self.worktrees:
                wt_id = wt.get("id", "")[:12]
                branch = wt.get("branch_name", "N/A")
                status = wt.get("status", "unknown")
                task_id = wt.get("task_id", "-")[:12] if wt.get("task_id") else "-"
                path = (
                    wt.get("path", "")[-30:] if len(wt.get("path", "")) > 30 else wt.get("path", "")
                )

                table.add_row(wt_id, branch, status, task_id, path, key=wt.get("id"))

        except Exception:
            pass  # nosec B110 - TUI update failure is non-critical

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle worktree selection."""
        self.selected_worktree_id = str(event.row_key.value) if event.row_key else None

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-create":
            self.notify("Worktree creation dialog coming soon", severity="information")

        elif button_id == "btn-cleanup":
            await self._cleanup_worktrees()

        elif button_id == "btn-refresh":
            self.loading = True
            await self.refresh_data()

    async def _cleanup_worktrees(self) -> None:
        """Clean up stale worktrees."""
        try:
            result = await self.api_client.call_tool(
                "gobby-worktrees",
                "cleanup_worktrees",
                {},
            )
            cleaned = result.get("cleaned", 0)
            self.notify(f"Cleaned up {cleaned} worktrees")

            await self.refresh_data()

        except Exception as e:
            self.notify(f"Cleanup failed: {e}", severity="error")

    def on_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle WebSocket events."""
        if event_type == "worktree_event":
            asyncio.create_task(self.refresh_data())
