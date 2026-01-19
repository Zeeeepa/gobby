"""Agents screen with running agents and spawn controls."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    LoadingIndicator,
    Select,
    Static,
    TextArea,
)

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.ws_client import GobbyWebSocketClient


class SpawnAgentDialog(Widget):
    """Dialog for spawning a new agent."""

    DEFAULT_CSS = """
    SpawnAgentDialog {
        width: 100%;
        height: auto;
        padding: 1;
        border: round #7c3aed;
        background: #1e1e2e;
    }

    SpawnAgentDialog .dialog-title {
        text-style: bold;
        color: #a78bfa;
        padding-bottom: 1;
    }

    SpawnAgentDialog .form-row {
        height: auto;
        margin-bottom: 1;
    }

    SpawnAgentDialog .form-label {
        color: #a6adc8;
        margin-bottom: 0;
    }

    SpawnAgentDialog #prompt-input {
        height: 5;
    }

    SpawnAgentDialog .button-row {
        layout: horizontal;
        height: 3;
        margin-top: 1;
    }

    SpawnAgentDialog .button-row Button {
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("🚀 Spawn New Agent", classes="dialog-title")

        with Vertical(classes="form-row"):
            yield Static("Prompt:", classes="form-label")
            yield TextArea(id="prompt-input")

        with Horizontal(classes="form-row"):
            with Vertical():
                yield Static("Mode:", classes="form-label")
                yield Select(
                    [
                        (label, value)
                        for label, value in [
                            ("Terminal", "terminal"),
                            ("Embedded", "embedded"),
                            ("Headless", "headless"),
                        ]
                    ],
                    value="terminal",
                    id="mode-select",
                )
            with Vertical():
                yield Static("Workflow:", classes="form-label")
                yield Select(
                    [
                        (label, value)
                        for label, value in [
                            ("None", ""),
                            ("Plan-Execute", "plan-execute"),
                            ("Test-Driven", "test-driven"),
                            ("Auto-Task", "auto-task"),
                        ]
                    ],
                    value="",
                    id="workflow-select",
                )

        with Horizontal(classes="button-row"):
            yield Button("Spawn", variant="primary", id="btn-spawn")
            yield Button("Cancel", id="btn-cancel-spawn")

    def get_values(self) -> dict[str, Any]:
        """Get the form values."""
        prompt = self.query_one("#prompt-input", TextArea).text
        mode = str(self.query_one("#mode-select", Select).value)
        workflow = str(self.query_one("#workflow-select", Select).value)
        return {"prompt": prompt, "mode": mode, "workflow": workflow or None}

    def clear(self) -> None:
        """Clear the form."""
        self.query_one("#prompt-input", TextArea).clear()


class AgentsScreen(Widget):
    """Agents screen showing running agents and spawn controls."""

    DEFAULT_CSS = """
    AgentsScreen {
        width: 1fr;
        height: 1fr;
    }

    AgentsScreen .screen-header {
        height: auto;
        padding: 1;
        background: #313244;
    }

    AgentsScreen .header-row {
        layout: horizontal;
    }

    AgentsScreen .panel-title {
        text-style: bold;
        color: #a78bfa;
        width: 1fr;
    }

    AgentsScreen #agents-table {
        height: 1fr;
    }

    AgentsScreen #spawn-dialog {
        display: none;
        margin: 1;
    }

    AgentsScreen #spawn-dialog.--visible {
        display: block;
    }

    AgentsScreen .loading-container {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }

    AgentsScreen .empty-state {
        content-align: center middle;
        height: 1fr;
        color: #a6adc8;
    }
    """

    loading = reactive(True)
    agents: reactive[list[dict[str, Any]]] = reactive(list)
    show_spawn_dialog = reactive(False)
    selected_agent_id: reactive[str | None] = reactive(None)

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
                yield Static("🤖 Agents", classes="panel-title")
                yield Button("+ Spawn Agent", variant="primary", id="btn-show-spawn")
                yield Button("Cancel Selected", id="btn-cancel-agent")
                yield Button("Refresh", id="btn-refresh")

        yield SpawnAgentDialog(id="spawn-dialog")

        if self.loading:
            with Container(classes="loading-container"):
                yield LoadingIndicator()
        else:
            yield DataTable(id="agents-table")

    async def on_mount(self) -> None:
        """Load data when mounted."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh agent list."""
        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                agents = await client.list_agents()
                self.agents = agents
        except Exception as e:
            self.notify(f"Failed to load agents: {e}", severity="error")
        finally:
            self.loading = False
            await self._setup_table()

    async def _setup_table(self) -> None:
        """Set up and populate the agents table."""
        try:
            table = self.query_one("#agents-table", DataTable)
            table.clear(columns=True)
            table.add_columns("ID", "Status", "Mode", "Prompt", "Duration")
            table.cursor_type = "row"

            for agent in self.agents:
                run_id = agent.get("run_id", "")[:12]
                status = agent.get("status", "unknown")
                mode = agent.get("mode", "?")
                prompt_val = agent.get("prompt") or ""
                prompt = prompt_val[:40] + "..." if len(prompt_val) > 40 else prompt_val

                # Calculate duration
                started = agent.get("started_at", "")
                if started and status == "running":
                    try:
                        started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                        duration = datetime.now(started_dt.tzinfo) - started_dt
                        duration_str = f"{duration.seconds // 60}m"
                    except Exception:
                        duration_str = "?"
                else:
                    duration_str = "-"

                table.add_row(run_id, status, mode, prompt, duration_str, key=agent.get("run_id"))

        except Exception:
            pass  # nosec B110 - TUI update failure is non-critical

    def watch_show_spawn_dialog(self, show: bool) -> None:
        """Toggle spawn dialog visibility."""
        try:
            dialog = self.query_one("#spawn-dialog", SpawnAgentDialog)
            dialog.set_class(show, "--visible")
        except Exception:
            pass  # nosec B110 - widget may not be mounted yet

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle agent selection."""
        self.selected_agent_id = str(event.row_key.value) if event.row_key else None

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-show-spawn":
            self.show_spawn_dialog = True

        elif button_id == "btn-cancel-spawn":
            self.show_spawn_dialog = False
            try:
                dialog = self.query_one("#spawn-dialog", SpawnAgentDialog)
                dialog.clear()
            except Exception:
                pass  # nosec B110 - widget may not be mounted yet

        elif button_id == "btn-spawn":
            await self._spawn_agent()

        elif button_id == "btn-cancel-agent":
            await self._cancel_agent()

        elif button_id == "btn-refresh":
            self.loading = True
            await self.refresh_data()

    async def _spawn_agent(self) -> None:
        """Spawn a new agent."""
        try:
            dialog = self.query_one("#spawn-dialog", SpawnAgentDialog)
            values = dialog.get_values()

            if not values.get("prompt"):
                self.notify("Prompt is required", severity="error")
                return

            async with GobbyAPIClient(self.api_client.base_url) as client:
                result = await client.start_agent(
                    prompt=values["prompt"],
                    mode=values["mode"],
                    workflow=values.get("workflow"),
                )
                self.notify(f"Agent spawned: {result.get('run_id', 'unknown')[:12]}")

            self.show_spawn_dialog = False
            dialog.clear()
            await self.refresh_data()

        except Exception as e:
            self.notify(f"Failed to spawn agent: {e}", severity="error")

    async def _cancel_agent(self) -> None:
        """Cancel the selected agent."""
        if not self.selected_agent_id:
            self.notify("No agent selected", severity="warning")
            return

        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                await client.cancel_agent(self.selected_agent_id)
                self.notify(f"Agent cancelled: {self.selected_agent_id[:12]}")

            await self.refresh_data()

        except Exception as e:
            self.notify(f"Failed to cancel agent: {e}", severity="error")

    def on_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle WebSocket events."""
        if event_type == "agent_event":
            self.run_worker(self.refresh_data(), name="refresh_data", exclusive=True)
