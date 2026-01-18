"""Sessions screen with list and search."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Input,
    LoadingIndicator,
    Select,
    Static,
)

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.ws_client import GobbyWebSocketClient

logger = logging.getLogger(__name__)


class SessionListPanel(Widget):
    """Panel displaying session list."""

    DEFAULT_CSS = """
    SessionListPanel {
        width: 1fr;
        height: 1fr;
        border-right: solid #45475a;
    }

    SessionListPanel .panel-header {
        height: auto;
        padding: 1;
        background: #313244;
    }

    SessionListPanel .search-row {
        layout: horizontal;
        height: 3;
    }

    SessionListPanel #session-search {
        width: 1fr;
        margin-right: 1;
    }

    SessionListPanel #status-filter {
        width: 20;
    }

    SessionListPanel #sessions-table {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel-header"):
            yield Static("📂 Sessions", classes="panel-title")
            with Horizontal(classes="search-row"):
                yield Input(placeholder="Search sessions...", id="session-search")
                yield Select(
                    [
                        (label, value)
                        for label, value in [
                            ("All", "all"),
                            ("Active", "active"),
                            ("Paused", "paused"),
                            ("Handoff Ready", "handoff_ready"),
                        ]
                    ],
                    value="all",
                    id="status-filter",
                )
        yield DataTable(id="sessions-table")

    def on_mount(self) -> None:
        """Set up the data table."""
        table = self.query_one("#sessions-table", DataTable)
        table.add_columns("ID", "Source", "Status", "Branch", "Age")
        table.cursor_type = "row"


class SessionDetailPanel(Widget):
    """Panel displaying session details."""

    DEFAULT_CSS = """
    SessionDetailPanel {
        width: 1fr;
        height: 1fr;
        padding: 1;
    }

    SessionDetailPanel .detail-header {
        height: auto;
        padding-bottom: 1;
    }

    SessionDetailPanel .detail-title {
        text-style: bold;
        color: #a78bfa;
    }

    SessionDetailPanel .detail-section {
        padding: 1 0;
    }

    SessionDetailPanel .detail-row {
        layout: horizontal;
        height: 1;
    }

    SessionDetailPanel .detail-label {
        color: #a6adc8;
        width: 14;
    }

    SessionDetailPanel .detail-value {
        width: 1fr;
    }

    SessionDetailPanel .context-section {
        padding: 1;
        border: round #45475a;
        height: auto;
        max-height: 15;
        overflow-y: auto;
    }

    SessionDetailPanel .action-buttons {
        layout: horizontal;
        height: 3;
        padding-top: 1;
    }

    SessionDetailPanel .action-buttons Button {
        margin-right: 1;
    }

    SessionDetailPanel .empty-state {
        content-align: center middle;
        height: 1fr;
        color: #a6adc8;
    }
    """

    session: reactive[dict[str, Any] | None] = reactive(None)

    def compose(self) -> ComposeResult:
        if self.session is None:
            yield Static("Select a session to view details", classes="empty-state")
        else:
            with Vertical(classes="detail-header"):
                yield Static(
                    self.session.get("title", "Untitled Session"),
                    classes="detail-title",
                )

            with Vertical(classes="detail-section"):
                details = [
                    ("ID", self.session.get("id", "")[:12] + "..."),
                    ("Source", self.session.get("source", "Unknown")),
                    ("Status", self.session.get("status", "unknown")),
                    ("Branch", self.session.get("git_branch", "N/A")),
                    (
                        "Project",
                        self.session.get("project_id", "N/A")[:12]
                        if self.session.get("project_id")
                        else "N/A",
                    ),
                    (
                        "Machine",
                        self.session.get("machine_id", "N/A")[:12]
                        if self.session.get("machine_id")
                        else "N/A",
                    ),
                ]
                for label, value in details:
                    with Horizontal(classes="detail-row"):
                        yield Static(f"{label}:", classes="detail-label")
                        yield Static(str(value), classes="detail-value")

            # Show compact context if available
            context = self.session.get("compact_markdown", "")
            if context:
                yield Static("Context:", classes="detail-label")
                yield Static(
                    context[:500] + "..." if len(context) > 500 else context,
                    classes="context-section",
                )

            with Horizontal(classes="action-buttons"):
                yield Button("Pickup", variant="primary", id="btn-pickup")
                yield Button("View Handoff", id="btn-handoff")

    def watch_session(self, session: dict[str, Any] | None) -> None:
        """Recompose when session changes."""

        def _handle_recompose_error(task: asyncio.Task[None]) -> None:
            if not task.cancelled() and task.exception():
                logger.error(f"Recompose failed: {task.exception()}", exc_info=task.exception())

        task = asyncio.create_task(self.recompose())
        task.add_done_callback(_handle_recompose_error)

    def update_session(self, session: dict[str, Any] | None) -> None:
        """Update the displayed session."""
        self.session = session


class SessionsScreen(Widget):
    """Sessions screen with list and detail view."""

    DEFAULT_CSS = """
    SessionsScreen {
        width: 1fr;
        height: 1fr;
    }

    SessionsScreen #sessions-container {
        layout: horizontal;
        height: 1fr;
    }

    SessionsScreen #list-panel {
        width: 55%;
    }

    SessionsScreen #detail-panel {
        width: 45%;
    }

    SessionsScreen .loading-container {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    loading = reactive(True)
    sessions: reactive[list[dict[str, Any]]] = reactive(list)
    selected_session_id: reactive[str | None] = reactive(None)
    current_filter = "all"
    search_query = ""

    def __init__(
        self,
        api_client: GobbyAPIClient,
        ws_client: GobbyWebSocketClient,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.api_client = api_client
        self.ws_client = ws_client
        self._session_map: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        if self.loading:
            with Container(classes="loading-container"):
                yield LoadingIndicator()
        else:
            with Horizontal(id="sessions-container"):
                yield SessionListPanel(id="list-panel")
                yield SessionDetailPanel(id="detail-panel")

    async def on_mount(self) -> None:
        """Load data when mounted."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh session list."""
        self.loading = True
        await self.recompose()

        try:
            status = None if self.current_filter == "all" else self.current_filter
            sessions = await self.api_client.list_sessions(status=status, limit=100)
            self.sessions = sessions
            self._session_map = {s.get("id", ""): s for s in sessions}

        except Exception as e:
            self.notify(f"Failed to load sessions: {e}", severity="error")
        finally:
            self.loading = False
            await self.recompose()
            self._populate_table()

    def _populate_table(self) -> None:
        """Populate the sessions table."""
        try:
            table = self.query_one("#sessions-table", DataTable)
            table.clear()

            # Filter by search query
            filtered = self.sessions
            if self.search_query:
                query = self.search_query.lower()
                filtered = [
                    s
                    for s in self.sessions
                    if query in s.get("id", "").lower()
                    or query in s.get("source", "").lower()
                    or query in s.get("title", "").lower()
                    or query in s.get("git_branch", "").lower()
                ]

            for session in filtered:
                session_id = session.get("id", "")[:12]
                source = session.get("source", "Unknown")[:12]
                status = session.get("status", "unknown")
                branch = session.get("git_branch", "N/A")[:15]

                # Calculate age
                created = session.get("created_at", "")
                if created:
                    try:
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        age = datetime.now(created_dt.tzinfo) - created_dt
                        if age.days > 0:
                            age_str = f"{age.days}d"
                        elif age.seconds > 3600:
                            age_str = f"{age.seconds // 3600}h"
                        else:
                            age_str = f"{age.seconds // 60}m"
                    except Exception:
                        age_str = "?"
                else:
                    age_str = "?"

                table.add_row(session_id, source, status, branch, age_str, key=session.get("id"))

        except Exception as e:
            logger.debug(f"Widget query failed (may not be mounted): {e}")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle session selection."""
        session_id = str(event.row_key.value) if event.row_key else None
        if session_id and session_id in self._session_map:
            self.selected_session_id = session_id
            session = self._session_map[session_id]
            try:
                detail_panel = self.query_one("#detail-panel", SessionDetailPanel)
                detail_panel.update_session(session)
            except Exception as e:
                logger.debug(f"Detail panel query failed (may not be mounted): {e}")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "session-search":
            self.search_query = event.value
            self._populate_table()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle filter changes."""

        def _handle_refresh_error(task: asyncio.Task[None]) -> None:
            if not task.cancelled() and task.exception():
                logger.error(f"Refresh failed: {task.exception()}", exc_info=task.exception())

        if event.select.id == "status-filter":
            self.current_filter = str(event.value)
            task = asyncio.create_task(self.refresh_data())
            task.add_done_callback(_handle_refresh_error)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle action button presses."""
        if not self.selected_session_id:
            return

        button_id = event.button.id

        try:
            if button_id == "btn-pickup":
                await self.api_client.call_tool(
                    "gobby-sessions",
                    "pickup",
                    {"session_id": self.selected_session_id},
                )
                self.notify(f"Session picked up: {self.selected_session_id[:12]}")

            elif button_id == "btn-handoff":
                result = await self.api_client.call_tool(
                    "gobby-sessions",
                    "get_handoff_context",
                    {"session_id": self.selected_session_id},
                )
                context = result.get("context", "No context available")
                self.notify(f"Handoff context: {len(context)} chars")

        except Exception as e:
            self.notify(f"Action failed: {e}", severity="error")

    def on_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle WebSocket events."""
        if event_type == "session_message" or event_type == "hook_event":
            # Refresh on session events
            asyncio.create_task(self.refresh_data())

    def activate_search(self) -> None:
        """Focus the search input."""
        try:
            search = self.query_one("#session-search", Input)
            search.focus()
        except Exception:
            pass  # nosec B110 - Widget may not be mounted yet
