"""Gobby TUI - Main application entry point."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Static

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.screens.agents import AgentsScreen
from gobby.tui.screens.chat import ChatScreen
from gobby.tui.screens.dashboard import DashboardScreen
from gobby.tui.screens.memory import MemoryScreen
from gobby.tui.screens.metrics import MetricsScreen
from gobby.tui.screens.orchestrator import OrchestratorScreen
from gobby.tui.screens.sessions import SessionsScreen
from gobby.tui.screens.tasks import TasksScreen
from gobby.tui.screens.workflows import WorkflowsScreen
from gobby.tui.screens.worktrees import WorktreesScreen
from gobby.tui.widgets.menu import MenuPanel
from gobby.tui.ws_client import GobbyWebSocketClient, WebSocketEventBridge


class GobbyHeader(Static):
    """Custom header with title and time."""

    DEFAULT_CSS = """
    GobbyHeader {
        dock: top;
        height: 3;
        background: #7c3aed;
        color: white;
        layout: horizontal;
    }

    GobbyHeader #header-title {
        width: 1fr;
        content-align: center middle;
        text-style: bold;
    }

    GobbyHeader #header-time {
        width: auto;
        padding: 0 2;
        content-align: center middle;
    }
    """

    current_time = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("GOBBY TUI", id="header-title")
        yield Static("", id="header-time")

    def on_mount(self) -> None:
        self.set_interval(1.0, self.update_time)
        self.update_time()

    def update_time(self) -> None:
        self.current_time = datetime.now().strftime("%H:%M:%S")
        self.query_one("#header-time", Static).update(self.current_time)


class GobbyFooter(Static):
    """Custom footer with key hints and connection status."""

    DEFAULT_CSS = """
    GobbyFooter {
        dock: bottom;
        height: 1;
        background: #313244;
        color: #a6adc8;
        layout: horizontal;
    }

    GobbyFooter #footer-hints {
        width: 1fr;
        padding: 0 1;
    }

    GobbyFooter #footer-status {
        width: auto;
        padding: 0 1;
    }

    GobbyFooter .connected {
        color: #22c55e;
    }

    GobbyFooter .disconnected {
        color: #ef4444;
    }
    """

    connected = reactive(False)

    def compose(self) -> ComposeResult:
        yield Static("[Q] Quit  [?] Help  [Tab] Focus  [/] Search", id="footer-hints")
        yield Static("Disconnected", id="footer-status", classes="disconnected")

    def watch_connected(self, connected: bool) -> None:
        status_widget = self.query_one("#footer-status", Static)
        if connected:
            status_widget.update("Connected")
            status_widget.remove_class("disconnected")
            status_widget.add_class("connected")
        else:
            status_widget.update("Disconnected")
            status_widget.remove_class("connected")
            status_widget.add_class("disconnected")


class ContentArea(Container):
    """Container for the main content area that switches screens."""

    DEFAULT_CSS = """
    ContentArea {
        width: 1fr;
        height: 1fr;
    }
    """


class GobbyApp(App[None]):
    """Gobby TUI Dashboard Application."""

    TITLE = "Gobby TUI"
    CSS_PATH = Path(__file__).parent / "styles" / "gobby.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help"),
        Binding("tab", "focus_next", "Focus Next"),
        Binding("shift+tab", "focus_previous", "Focus Previous"),
        Binding("slash", "search", "Search"),
        Binding("r", "refresh", "Refresh"),
        # Screen navigation
        Binding("d", "switch_screen('dashboard')", "Dashboard", show=False),
        Binding("t", "switch_screen('tasks')", "Tasks", show=False),
        Binding("s", "switch_screen('sessions')", "Sessions", show=False),
        Binding("c", "switch_screen('chat')", "Chat", show=False),
        Binding("a", "switch_screen('agents')", "Agents", show=False),
        Binding("w", "switch_screen('worktrees')", "Worktrees", show=False),
        Binding("f", "switch_screen('workflows')", "Workflows", show=False),
        Binding("m", "switch_screen('memory')", "Memory", show=False),
        Binding("e", "switch_screen('metrics')", "Metrics", show=False),
        Binding("o", "switch_screen('orchestrator')", "Orchestrator", show=False),
    ]

    current_screen_id = reactive("dashboard")

    def __init__(
        self,
        daemon_url: str = "http://localhost:8765",
        ws_url: str = "ws://localhost:8766",
    ) -> None:
        super().__init__()
        self.daemon_url = daemon_url
        self.ws_url = ws_url

        # API and WebSocket clients
        self.api_client = GobbyAPIClient(daemon_url)
        self.ws_client = GobbyWebSocketClient(ws_url)
        self.ws_bridge = WebSocketEventBridge(self.ws_client)

        # Screen instances (created lazily)
        self._screens: dict[str, Any] = {}

        # WebSocket task
        self._ws_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        yield GobbyHeader()
        with Horizontal():
            yield MenuPanel(id="menu-panel")
            yield ContentArea(id="content-area")
        yield GobbyFooter(id="footer")

    async def on_mount(self) -> None:
        """Initialize the app on mount."""
        # Set up WebSocket event bridge
        self.ws_bridge.bind_app(self)
        self.ws_bridge.setup_handlers()

        # Register connection callbacks
        self.ws_client.on_connect(self._on_ws_connect)
        self.ws_client.on_disconnect(self._on_ws_disconnect)

        # Subscribe to events
        await self.ws_client.subscribe(
            [
                "hook_event",
                "agent_event",
                "autonomous_event",
                "session_message",
                "worktree_event",
            ]
        )

        # Start WebSocket connection in background
        self._ws_task = asyncio.create_task(self._connect_ws())

        # Show initial screen
        await self._show_screen("dashboard")

    async def _connect_ws(self) -> None:
        """Connect to WebSocket server."""
        try:
            await self.ws_client.connect()
        except Exception as e:
            self.log.error(f"WebSocket connection failed: {e}")

    def _on_ws_connect(self) -> None:
        """Handle WebSocket connection established."""
        footer = self.query_one("#footer", GobbyFooter)
        footer.connected = True

    def _on_ws_disconnect(self) -> None:
        """Handle WebSocket disconnection."""
        footer = self.query_one("#footer", GobbyFooter)
        footer.connected = False

    def post_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle WebSocket events posted from the bridge."""
        # Dispatch to current screen if it has a handler
        content_area = self.query_one("#content-area", ContentArea)
        for child in content_area.children:
            if hasattr(child, "on_ws_event"):
                child.on_ws_event(event_type, data)

    async def _show_screen(self, screen_id: str) -> None:
        """Show a screen in the content area."""
        content_area = self.query_one("#content-area", ContentArea)

        # Clear current content
        await content_area.remove_children()

        # Create or get screen instance
        screen = self._get_or_create_screen(screen_id)

        # Mount the screen widget
        await content_area.mount(screen)

        # Update menu selection
        menu = self.query_one("#menu-panel", MenuPanel)
        menu.current_screen = screen_id

        self.current_screen_id = screen_id

    def _get_or_create_screen(self, screen_id: str) -> Any:
        """Get or create a screen instance."""
        if screen_id not in self._screens:
            screen_class = self._get_screen_class(screen_id)
            self._screens[screen_id] = screen_class(
                api_client=self.api_client,
                ws_client=self.ws_client,
            )
        return self._screens[screen_id]

    def _get_screen_class(self, screen_id: str) -> type:
        """Get the screen class for a screen ID."""
        screen_map = {
            "dashboard": DashboardScreen,
            "tasks": TasksScreen,
            "sessions": SessionsScreen,
            "chat": ChatScreen,
            "agents": AgentsScreen,
            "worktrees": WorktreesScreen,
            "workflows": WorkflowsScreen,
            "memory": MemoryScreen,
            "metrics": MetricsScreen,
            "orchestrator": OrchestratorScreen,
        }
        return screen_map.get(screen_id, DashboardScreen)

    async def action_switch_screen(self, screen_id: str) -> None:
        """Switch to a different screen."""
        await self._show_screen(screen_id)

    async def action_refresh(self) -> None:
        """Refresh the current screen."""
        content_area = self.query_one("#content-area", ContentArea)
        for child in content_area.children:
            if hasattr(child, "refresh_data"):
                await child.refresh_data()

    def action_help(self) -> None:
        """Show help overlay."""
        self.notify(
            "Help: Press D/T/S/C/A/W/F/M/E/O to switch screens. Q to quit.",
            title="Keyboard Shortcuts",
        )

    def action_search(self) -> None:
        """Activate search in current screen."""
        content_area = self.query_one("#content-area", ContentArea)
        for child in content_area.children:
            if hasattr(child, "activate_search"):
                child.activate_search()

    def on_menu_panel_item_selected(self, event: MenuPanel.ItemSelected) -> None:
        """Handle menu item selection."""
        self.run_worker(self._show_screen(event.item.screen_id))

    async def on_unmount(self) -> None:
        """Clean up on app exit."""
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        await self.ws_client.disconnect()


def run_tui(daemon_url: str = "http://localhost:8765", ws_url: str = "ws://localhost:8766") -> None:
    """Entry point for the TUI application."""
    app = GobbyApp(daemon_url=daemon_url, ws_url=ws_url)
    app.run()
