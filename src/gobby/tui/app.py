"""Main Gobby TUI Application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive

from gobby.tui.client import DaemonClient
from gobby.tui.views.sessions import SessionsView
from gobby.tui.widgets.command_input import CommandInput
from gobby.tui.widgets.filter_tabs import FilterTabs
from gobby.tui.widgets.footer import StatusFooter
from gobby.tui.widgets.header import GobbyHeader
from gobby.tui.widgets.log_panel import LogPanel


class GobbyApp(App):
    """Gobby TUI Application."""

    CSS_PATH = "gobby.tcss"
    TITLE = "Gobby"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("s", "switch_view('sessions')", "Sessions"),
        Binding("t", "switch_view('tasks')", "Tasks"),
        Binding("a", "switch_view('agents')", "Agents"),
        Binding("m", "switch_view('memory')", "Memory"),
        Binding("?", "show_help", "Help"),
        Binding("escape", "unfocus", "Unfocus"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding(":", "focus_command", "Command", show=False),
    ]

    # Reactive state
    current_view: reactive[str] = reactive("sessions")
    daemon_connected: reactive[bool] = reactive(False)

    def __init__(
        self,
        daemon_url: str = "http://localhost:8765",
        ws_url: str = "ws://localhost:8766",
    ) -> None:
        """Initialize the Gobby TUI.

        Args:
            daemon_url: URL for daemon HTTP API
            ws_url: URL for daemon WebSocket
        """
        super().__init__()
        self.daemon_url = daemon_url
        self.ws_url = ws_url
        self.client = DaemonClient(http_base=daemon_url, ws_base=ws_url)

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield GobbyHeader(connected=False)
        yield FilterTabs()
        yield SessionsView(client=self.client, id="sessions-view")
        yield LogPanel()
        yield CommandInput()
        yield StatusFooter()

    async def on_mount(self) -> None:
        """Initialize the app when mounted."""
        # Get log panel for logging
        log_panel = self.query_one(LogPanel)
        log_panel.log_info("Starting Gobby TUI...")

        # Try to connect to daemon
        connected = await self.client.connect()
        self.daemon_connected = connected

        # Update header connection status
        header = self.query_one(GobbyHeader)
        header.set_connected(connected)

        if connected:
            log_panel.log_success("Connected to Gobby daemon")
            # Load initial data
            sessions_view = self.query_one(SessionsView)
            await sessions_view.refresh_data()
            log_panel.log_info("Sessions loaded")
        else:
            log_panel.log_error("Failed to connect to daemon")
            log_panel.log_info("Make sure gobby daemon is running: gobby start")

        # Get git branch for footer
        footer = self.query_one(StatusFooter)
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                footer.set_branch(branch)
        except Exception:
            pass

    def on_filter_tabs_filter_changed(self, event: FilterTabs.FilterChanged) -> None:
        """Handle filter tab changes.

        Args:
            event: The filter changed event
        """
        sessions_view = self.query_one(SessionsView)
        sessions_view.filter_status = event.filter_value

        log_panel = self.query_one(LogPanel)
        log_panel.log_info(f"Filter changed to: {event.filter_value}")

    def on_command_input_command_submitted(
        self, event: CommandInput.CommandSubmitted
    ) -> None:
        """Handle command submission.

        Args:
            event: The command submitted event
        """
        command = event.command.lower().strip()
        log_panel = self.query_one(LogPanel)

        if command in ("q", "quit", "exit"):
            self.exit()
        elif command in ("r", "refresh"):
            self.action_refresh()
        elif command in ("h", "help", "?"):
            log_panel.log_info("Commands: quit, refresh, help")
            log_panel.log_info("Keys: q=quit, r=refresh, j/k=navigate, ?=help")
        else:
            log_panel.log_warning(f"Unknown command: {command}")

    async def action_refresh(self) -> None:
        """Refresh the current view."""
        log_panel = self.query_one(LogPanel)
        log_panel.log_info("Refreshing...")

        if self.current_view == "sessions":
            sessions_view = self.query_one(SessionsView)
            await sessions_view.refresh_data()
            log_panel.log_success("Sessions refreshed")

    def action_cursor_down(self) -> None:
        """Move cursor down in the current view."""
        if self.current_view == "sessions":
            sessions_view = self.query_one(SessionsView)
            sessions_view.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the current view."""
        if self.current_view == "sessions":
            sessions_view = self.query_one(SessionsView)
            sessions_view.action_cursor_up()

    def action_focus_command(self) -> None:
        """Focus the command input."""
        command_input = self.query_one(CommandInput)
        command_input.focus_input()

    def action_unfocus(self) -> None:
        """Remove focus from current widget."""
        self.set_focus(None)

    def action_switch_view(self, view_name: str) -> None:
        """Switch to a different view.

        Args:
            view_name: The view to switch to
        """
        log_panel = self.query_one(LogPanel)
        log_panel.log_info(f"View: {view_name} (not yet implemented)")
        # TODO: Implement view switching when other views are added

    def action_show_help(self) -> None:
        """Show help information."""
        log_panel = self.query_one(LogPanel)
        log_panel.log_info("=== Gobby TUI Help ===")
        log_panel.log_info("Navigation: j/k or arrow keys")
        log_panel.log_info("Views: s=Sessions, t=Tasks, a=Agents, m=Memory")
        log_panel.log_info("Actions: r=Refresh, q=Quit, :=Command mode")


def run_tui(
    daemon_url: str = "http://localhost:8765",
    ws_url: str = "ws://localhost:8766",
) -> None:
    """Run the Gobby TUI.

    Args:
        daemon_url: URL for daemon HTTP API
        ws_url: URL for daemon WebSocket
    """
    app = GobbyApp(daemon_url=daemon_url, ws_url=ws_url)
    app.run()
