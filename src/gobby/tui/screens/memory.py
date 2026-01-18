"""Memory screen with search and list."""

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
    Input,
    LoadingIndicator,
    Static,
)

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.ws_client import GobbyWebSocketClient


class MemoryDetailPanel(Widget):
    """Panel showing memory item details."""

    DEFAULT_CSS = """
    MemoryDetailPanel {
        width: 40%;
        height: 1fr;
        padding: 1;
        border-left: solid #45475a;
    }

    MemoryDetailPanel .detail-title {
        text-style: bold;
        color: #a78bfa;
        padding-bottom: 1;
    }

    MemoryDetailPanel .detail-row {
        layout: horizontal;
        height: 1;
    }

    MemoryDetailPanel .detail-label {
        color: #a6adc8;
        width: 12;
    }

    MemoryDetailPanel .detail-value {
        width: 1fr;
    }

    MemoryDetailPanel .content-area {
        height: 1fr;
        padding: 1;
        border: round #45475a;
        overflow-y: auto;
    }

    MemoryDetailPanel .empty-state {
        content-align: center middle;
        height: 1fr;
        color: #a6adc8;
    }
    """

    memory: reactive[dict[str, Any] | None] = reactive(None)

    def compose(self) -> ComposeResult:
        if self.memory is None:
            yield Static("Select a memory to view details", classes="empty-state")
        else:
            yield Static("📝 Memory Details", classes="detail-title")

            with Horizontal(classes="detail-row"):
                yield Static("ID:", classes="detail-label")
                yield Static(self.memory.get("id", "")[:16], classes="detail-value")

            with Horizontal(classes="detail-row"):
                yield Static("Importance:", classes="detail-label")
                importance = self.memory.get("importance", 0.5)
                yield Static(f"{importance:.2f}", classes="detail-value")

            with Horizontal(classes="detail-row"):
                yield Static("Created:", classes="detail-label")
                created = self.memory.get("created_at", "")[:19]
                yield Static(created, classes="detail-value")

            yield Static("Content:", classes="detail-label")
            yield Static(self.memory.get("content", ""), classes="content-area")

    def watch_memory(self, memory: dict[str, Any] | None) -> None:
        """Recompose when memory changes."""
        self.call_after_refresh(self.recompose)


class MemoryScreen(Widget):
    """Memory screen with search and list."""

    DEFAULT_CSS = """
    MemoryScreen {
        width: 1fr;
        height: 1fr;
    }

    MemoryScreen .screen-header {
        height: auto;
        padding: 1;
        background: #313244;
    }

    MemoryScreen .header-row {
        layout: horizontal;
    }

    MemoryScreen .panel-title {
        text-style: bold;
        color: #a78bfa;
        width: 1fr;
    }

    MemoryScreen .search-row {
        layout: horizontal;
        height: 3;
        margin-top: 1;
    }

    MemoryScreen #search-input {
        width: 1fr;
        margin-right: 1;
    }

    MemoryScreen #content-container {
        layout: horizontal;
        height: 1fr;
    }

    MemoryScreen #memories-table {
        width: 60%;
        height: 1fr;
    }

    MemoryScreen .loading-container {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    loading = reactive(True)
    memories: reactive[list[dict[str, Any]]] = reactive(list)
    selected_memory_id: reactive[str | None] = reactive(None)
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
        self._memory_map: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        with Vertical(classes="screen-header"):
            with Horizontal(classes="header-row"):
                yield Static("🧠 Memory", classes="panel-title")
                yield Button("+ Remember", variant="primary", id="btn-remember")
                yield Button("Forget", id="btn-forget")
                yield Button("Refresh", id="btn-refresh")
            with Horizontal(classes="search-row"):
                yield Input(placeholder="Search memories...", id="search-input")
                yield Button("Search", id="btn-search")

        if self.loading:
            with Container(classes="loading-container"):
                yield LoadingIndicator()
        else:
            with Horizontal(id="content-container"):
                yield DataTable(id="memories-table")
                yield MemoryDetailPanel(id="detail-panel")

    async def on_mount(self) -> None:
        """Load data when mounted."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh memory list."""
        try:
            if self.search_query:
                memories = await self.api_client.recall(self.search_query, limit=50)
            else:
                result = await self.api_client.call_tool(
                    "gobby-memory",
                    "list_memories",
                    {"limit": 50},
                )
                memories = result.get("memories", [])

            self.memories = memories
            self._memory_map = {m.get("id", ""): m for m in memories}

        except Exception as e:
            self.notify(f"Failed to load memories: {e}", severity="error")
        finally:
            self.loading = False
            await self.recompose()
            await self._setup_table()

    async def _setup_table(self) -> None:
        """Set up and populate the memories table."""
        try:
            table = self.query_one("#memories-table", DataTable)
            table.clear(columns=True)
            table.add_columns("ID", "Content", "Importance")
            table.cursor_type = "row"

            for memory in self.memories:
                mem_id = memory.get("id", "")[:12]
                content = memory.get("content", "")[:40]
                if len(memory.get("content", "")) > 40:
                    content += "..."
                importance = f"{memory.get('importance', 0.5):.2f}"

                table.add_row(mem_id, content, importance, key=memory.get("id"))

        except Exception:
            pass  # nosec B110 - TUI update failure is non-critical

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle memory selection."""
        memory_id = str(event.row_key.value) if event.row_key else None
        if memory_id and memory_id in self._memory_map:
            self.selected_memory_id = memory_id
            try:
                panel = self.query_one("#detail-panel", MemoryDetailPanel)
                panel.memory = self._memory_map[memory_id]
            except Exception:
                pass  # nosec B110 - Widget may not be mounted yet

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-remember":
            self.notify("Remember dialog coming soon", severity="information")

        elif button_id == "btn-forget":
            await self._forget_memory()

        elif button_id == "btn-search":
            await self._do_search()

        elif button_id == "btn-refresh":
            self.search_query = ""
            self.loading = True
            await self.refresh_data()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search submission."""
        if event.input.id == "search-input":
            asyncio.create_task(self._do_search())

    async def _do_search(self) -> None:
        """Perform memory search."""
        try:
            search_input = self.query_one("#search-input", Input)
            self.search_query = search_input.value
            self.loading = True
            await self.refresh_data()
        except Exception:
            pass  # nosec B110 - Search failure handled by refresh_data

    async def _forget_memory(self) -> None:
        """Forget the selected memory."""
        if not self.selected_memory_id:
            self.notify("No memory selected", severity="warning")
            return

        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                await client.call_tool(
                    "gobby-memory",
                    "forget",
                    {"memory_id": self.selected_memory_id},
                )
                self.notify("Memory forgotten")

            self.selected_memory_id = None
            await self.refresh_data()

        except Exception as e:
            self.notify(f"Failed to forget memory: {e}", severity="error")

    def activate_search(self) -> None:
        """Focus the search input."""
        try:
            search = self.query_one("#search-input", Input)
            search.focus()
        except Exception:
            pass  # nosec B110 - Widget may not be mounted yet
