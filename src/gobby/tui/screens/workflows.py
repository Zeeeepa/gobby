"""Workflows screen with active workflow state visualization."""

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
    Select,
    Static,
)

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.ws_client import GobbyWebSocketClient


class WorkflowStatePanel(Widget):
    """Panel showing current workflow state."""

    DEFAULT_CSS = """
    WorkflowStatePanel {
        height: auto;
        padding: 1;
        border: round #7c3aed;
        margin: 1;
    }

    WorkflowStatePanel .state-title {
        text-style: bold;
        color: #a78bfa;
        padding-bottom: 1;
    }

    WorkflowStatePanel .state-row {
        layout: horizontal;
        height: 1;
    }

    WorkflowStatePanel .state-label {
        color: #a6adc8;
        width: 16;
    }

    WorkflowStatePanel .state-value {
        width: 1fr;
    }

    WorkflowStatePanel .state-active {
        color: #22c55e;
    }

    WorkflowStatePanel .state-inactive {
        color: #6c7086;
    }
    """

    workflow_status: reactive[dict[str, Any] | None] = reactive(None)

    def compose(self) -> ComposeResult:
        yield Static("⚙️ Active Workflow", classes="state-title")

        if self.workflow_status is None:
            yield Static("No workflow active", classes="state-inactive")
        else:
            workflow = self.workflow_status.get("workflow")
            if workflow:
                with Horizontal(classes="state-row"):
                    yield Static("Workflow:", classes="state-label")
                    yield Static(
                        workflow.get("name", "Unknown"), classes="state-value state-active"
                    )
                with Horizontal(classes="state-row"):
                    yield Static("Current Step:", classes="state-label")
                    yield Static(workflow.get("current_step", "N/A"), classes="state-value")
                with Horizontal(classes="state-row"):
                    yield Static("Type:", classes="state-label")
                    yield Static(workflow.get("type", "unknown"), classes="state-value")
            else:
                yield Static("No workflow active", classes="state-inactive")

    def watch_workflow_status(self, status: dict[str, Any] | None) -> None:
        """Recompose when status changes."""
        asyncio.create_task(self.recompose())


class WorkflowsScreen(Widget):
    """Workflows screen showing workflow state and controls."""

    DEFAULT_CSS = """
    WorkflowsScreen {
        width: 1fr;
        height: 1fr;
    }

    WorkflowsScreen .screen-header {
        height: auto;
        padding: 1;
        background: #313244;
    }

    WorkflowsScreen .header-row {
        layout: horizontal;
    }

    WorkflowsScreen .panel-title {
        text-style: bold;
        color: #a78bfa;
        width: 1fr;
    }

    WorkflowsScreen #workflow-selector {
        width: 30;
        margin-right: 1;
    }

    WorkflowsScreen .content-area {
        height: 1fr;
        padding: 1;
    }

    WorkflowsScreen #available-workflows {
        height: 1fr;
    }

    WorkflowsScreen .loading-container {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    loading = reactive(True)
    workflow_status: reactive[dict[str, Any] | None] = reactive(None)
    available_workflows: reactive[list[str]] = reactive(list)

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
                yield Static("🔄 Workflows", classes="panel-title")
                yield Select(
                    [(name, name) for name in self.available_workflows] or [("None", "")],
                    value="",
                    id="workflow-selector",
                )
                yield Button("Activate", variant="primary", id="btn-activate")
                yield Button("Clear", id="btn-clear")
                yield Button("Refresh", id="btn-refresh")

        if self.loading:
            with Container(classes="loading-container"):
                yield LoadingIndicator()
        else:
            with Vertical(classes="content-area"):
                yield WorkflowStatePanel(id="state-panel")
                yield Static("Available Workflows", classes="panel-title")
                yield DataTable(id="available-workflows")

    async def on_mount(self) -> None:
        """Load data when mounted."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh workflow status."""
        workflows: list[dict[str, Any]] = []
        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                status = await client.get_workflow_status()
                self.workflow_status = status

                # Get available workflows list
                result = await client.call_tool(
                    "gobby-workflows",
                    "list_workflows",
                    {},
                )
                workflows = result.get("workflows", [])
                self.available_workflows = [w.get("name", "") for w in workflows if w.get("name")]

        except Exception as e:
            self.notify(f"Failed to load workflow status: {e}", severity="error")
        finally:
            self.loading = False
            await self.recompose()
            await self._update_state_panel()
            await self._setup_table(workflows)

    async def _update_state_panel(self) -> None:
        """Update the workflow state panel."""
        try:
            panel = self.query_one("#state-panel", WorkflowStatePanel)
            panel.workflow_status = self.workflow_status
        except Exception:
            pass  # Widget may not be mounted yet

    async def _setup_table(self, workflows: list[dict[str, Any]] | None = None) -> None:
        """Set up the available workflows table."""
        try:
            table = self.query_one("#available-workflows", DataTable)
            table.clear(columns=True)
            table.add_columns("Name", "Type", "Description")
            table.cursor_type = "row"

            # Use provided workflows instead of fetching again
            if workflows is None:
                workflows = []

            for wf in workflows:
                name = wf.get("name", "Unknown")
                wf_type = wf.get("type", "unknown")
                desc = wf.get("description", "")[:50]
                table.add_row(name, wf_type, desc, key=name)

        except Exception:
            pass  # TUI update failure is non-critical

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-activate":
            await self._activate_workflow()

        elif button_id == "btn-clear":
            await self._clear_workflow()

        elif button_id == "btn-refresh":
            self.loading = True
            await self.refresh_data()

    async def _activate_workflow(self) -> None:
        """Activate the selected workflow."""
        try:
            selector = self.query_one("#workflow-selector", Select)
            workflow_name = str(selector.value)

            if not workflow_name:
                self.notify("Select a workflow first", severity="warning")
                return

            async with GobbyAPIClient(self.api_client.base_url) as client:
                await client.activate_workflow(workflow_name)
                self.notify(f"Activated workflow: {workflow_name}")

            await self.refresh_data()

        except Exception as e:
            self.notify(f"Failed to activate workflow: {e}", severity="error")

    async def _clear_workflow(self) -> None:
        """Clear the active workflow."""
        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                await client.call_tool(
                    "gobby-workflows",
                    "deactivate_workflow",
                    {},
                )
                self.notify("Workflow cleared")

            await self.refresh_data()

        except Exception as e:
            self.notify(f"Failed to clear workflow: {e}", severity="error")

    def on_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle WebSocket events."""
        # Refresh on workflow-related events
        if event_type == "hook_event":
            asyncio.create_task(self.refresh_data())
