"""Tasks screen with tree view and detail panel."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    LoadingIndicator,
    Select,
    Static,
    Tree,
)
from textual.widgets.tree import TreeNode

from gobby.tui.api_client import GobbyAPIClient
from gobby.tui.ws_client import GobbyWebSocketClient


class TaskTreePanel(Widget):
    """Panel displaying task tree with filtering."""

    DEFAULT_CSS = """
    TaskTreePanel {
        width: 1fr;
        height: 1fr;
        border-right: solid #45475a;
    }

    TaskTreePanel .panel-header {
        height: auto;
        padding: 1;
        background: #313244;
    }

    TaskTreePanel .filter-row {
        layout: horizontal;
        height: 3;
    }

    TaskTreePanel .filter-select {
        width: 1fr;
        margin-right: 1;
    }

    TaskTreePanel #task-tree {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel-header"):
            yield Static("📋 Tasks", classes="panel-title")
            with Horizontal(classes="filter-row"):
                yield Select(
                    [(label, value) for label, value in [
                        ("All Status", "all"),
                        ("Open", "open"),
                        ("In Progress", "in_progress"),
                        ("Review", "review"),
                        ("Closed", "closed"),
                    ]],
                    value="all",
                    id="status-filter",
                    classes="filter-select",
                )
                yield Select(
                    [(label, value) for label, value in [
                        ("All Types", "all"),
                        ("Task", "task"),
                        ("Bug", "bug"),
                        ("Feature", "feature"),
                        ("Epic", "epic"),
                    ]],
                    value="all",
                    id="type-filter",
                    classes="filter-select",
                )
        yield Tree("Tasks", id="task-tree")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle filter changes."""
        self.post_message(TasksScreen.FilterChanged(
            status=self.query_one("#status-filter", Select).value,
            task_type=self.query_one("#type-filter", Select).value,
        ))


class TaskDetailPanel(Widget):
    """Panel displaying task details."""

    DEFAULT_CSS = """
    TaskDetailPanel {
        width: 1fr;
        height: 1fr;
        padding: 1;
    }

    TaskDetailPanel .detail-header {
        height: auto;
        padding-bottom: 1;
    }

    TaskDetailPanel .detail-title {
        text-style: bold;
        color: #a78bfa;
    }

    TaskDetailPanel .detail-ref {
        color: #06b6d4;
    }

    TaskDetailPanel .detail-section {
        padding: 1 0;
    }

    TaskDetailPanel .detail-label {
        color: #a6adc8;
        width: 12;
    }

    TaskDetailPanel .detail-value {
        width: 1fr;
    }

    TaskDetailPanel .detail-description {
        padding: 1;
        border: round #45475a;
        height: auto;
        max-height: 10;
    }

    TaskDetailPanel .action-buttons {
        layout: horizontal;
        height: 3;
        padding-top: 1;
    }

    TaskDetailPanel .action-buttons Button {
        margin-right: 1;
    }

    TaskDetailPanel .empty-state {
        content-align: center middle;
        height: 1fr;
        color: #a6adc8;
    }
    """

    task: reactive[dict[str, Any] | None] = reactive(None)

    def compose(self) -> ComposeResult:
        if self.task is None:
            yield Static("Select a task to view details", classes="empty-state")
        else:
            with Vertical(classes="detail-header"):
                yield Static(self.task.get("title", "Untitled"), classes="detail-title")
                yield Static(self.task.get("ref", ""), classes="detail-ref")

            with Vertical(classes="detail-section"):
                with Horizontal():
                    yield Static("Status:", classes="detail-label")
                    yield Static(self.task.get("status", "unknown"), classes="detail-value", id="detail-status")
                with Horizontal():
                    yield Static("Type:", classes="detail-label")
                    yield Static(self.task.get("task_type", "task"), classes="detail-value")
                with Horizontal():
                    yield Static("Priority:", classes="detail-label")
                    yield Static(str(self.task.get("priority", 3)), classes="detail-value")
                with Horizontal():
                    yield Static("Assignee:", classes="detail-label")
                    yield Static(self.task.get("assignee", "Unassigned"), classes="detail-value")

            if self.task.get("description"):
                yield Static("Description:", classes="detail-label")
                yield Static(self.task.get("description", ""), classes="detail-description")

            with Horizontal(classes="action-buttons"):
                status = self.task.get("status", "")
                if status == "open":
                    yield Button("Start", variant="primary", id="btn-start")
                    yield Button("Expand", id="btn-expand")
                elif status == "in_progress":
                    yield Button("Complete", variant="success", id="btn-complete")
                elif status == "review":
                    yield Button("Approve", variant="success", id="btn-approve")
                    yield Button("Reopen", variant="error", id="btn-reopen")

    def watch_task(self, task: dict[str, Any] | None) -> None:
        """Recompose when task changes."""
        asyncio.create_task(self.recompose())

    def update_task(self, task: dict[str, Any] | None) -> None:
        """Update the displayed task."""
        self.task = task


class TasksScreen(Widget):
    """Tasks screen with tree view and detail panel."""

    DEFAULT_CSS = """
    TasksScreen {
        width: 1fr;
        height: 1fr;
    }

    TasksScreen #tasks-container {
        layout: horizontal;
        height: 1fr;
    }

    TasksScreen #tree-panel {
        width: 50%;
    }

    TasksScreen #detail-panel {
        width: 50%;
    }

    TasksScreen .loading-container {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    from dataclasses import dataclass

    from textual.message import Message

    @dataclass
    class FilterChanged(Message):
        """Message sent when filters change."""
        status: str
        task_type: str

    @dataclass
    class TaskSelected(Message):
        """Message sent when a task is selected."""
        task_id: str

    loading = reactive(True)
    tasks: reactive[list[dict[str, Any]]] = reactive(list)
    selected_task_id: reactive[str | None] = reactive(None)
    current_filter_status = "all"
    current_filter_type = "all"

    def __init__(
        self,
        api_client: GobbyAPIClient,
        ws_client: GobbyWebSocketClient,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_client = api_client
        self.ws_client = ws_client
        self._task_map: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        if self.loading:
            with Container(classes="loading-container"):
                yield LoadingIndicator()
        else:
            with Horizontal(id="tasks-container"):
                yield TaskTreePanel(id="tree-panel")
                yield TaskDetailPanel(id="detail-panel")

    async def on_mount(self) -> None:
        """Load data when mounted."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh task list."""
        self.loading = True
        await self.recompose()

        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                # Build filter args
                args: dict[str, Any] = {}
                if self.current_filter_status != "all":
                    args["status"] = self.current_filter_status
                if self.current_filter_type != "all":
                    args["task_type"] = self.current_filter_type

                tasks = await client.list_tasks(**args)
                self.tasks = tasks
                self._task_map = {t.get("id", ""): t for t in tasks}

        except Exception as e:
            self.notify(f"Failed to load tasks: {e}", severity="error")
        finally:
            self.loading = False
            await self.recompose()
            self._populate_tree()

    def _populate_tree(self) -> None:
        """Populate the task tree with loaded tasks."""
        try:
            tree = self.query_one("#task-tree", Tree)
            tree.clear()

            # Build parent -> children mapping
            children_map: dict[str | None, list[dict[str, Any]]] = {}
            for task in self.tasks:
                parent_id = task.get("parent_id")
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(task)

            # Add root level tasks
            root_tasks = children_map.get(None, [])
            for task in sorted(root_tasks, key=lambda t: t.get("priority", 3)):
                self._add_task_to_tree(tree.root, task, children_map)

            tree.root.expand()

        except Exception:
            pass

    def _add_task_to_tree(
        self,
        parent: TreeNode,
        task: dict[str, Any],
        children_map: dict[str | None, list[dict[str, Any]]],
    ) -> None:
        """Recursively add a task and its children to the tree."""
        status = task.get("status", "open")
        status_icon = {
            "open": "○",
            "in_progress": "◐",
            "review": "◑",
            "closed": "●",
        }.get(status, "○")

        ref = task.get("ref", "")
        title = task.get("title", "Untitled")
        label = f"{status_icon} {ref} {title}"

        node = parent.add(label, data=task.get("id"))

        # Add children
        task_id = task.get("id")
        children = children_map.get(task_id, [])
        for child in sorted(children, key=lambda t: t.get("priority", 3)):
            self._add_task_to_tree(node, child, children_map)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle task selection in tree."""
        task_id = event.node.data
        if task_id and task_id in self._task_map:
            self.selected_task_id = task_id
            task = self._task_map[task_id]
            try:
                detail_panel = self.query_one("#detail-panel", TaskDetailPanel)
                detail_panel.update_task(task)
            except Exception:
                pass

    async def on_filter_changed(self, event: FilterChanged) -> None:
        """Handle filter changes."""
        self.current_filter_status = event.status if event.status != "all" else "all"
        self.current_filter_type = event.task_type if event.task_type != "all" else "all"
        await self.refresh_data()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle action button presses."""
        if not self.selected_task_id:
            return

        button_id = event.button.id
        task_id = self.selected_task_id

        try:
            async with GobbyAPIClient(self.api_client.base_url) as client:
                if button_id == "btn-start":
                    await client.update_task(task_id, status="in_progress")
                    self.notify(f"Task started: {task_id}")

                elif button_id == "btn-expand":
                    await client.call_tool(
                        "gobby-tasks",
                        "expand_task",
                        {"task_id": task_id},
                    )
                    self.notify(f"Task expanded: {task_id}")

                elif button_id == "btn-complete":
                    # Note: In real usage, this would need a commit SHA
                    await client.close_task(task_id, no_commit_needed=True)
                    self.notify(f"Task completed: {task_id}")

                elif button_id == "btn-approve":
                    await client.close_task(task_id, no_commit_needed=True)
                    self.notify(f"Task approved: {task_id}")

                elif button_id == "btn-reopen":
                    await client.call_tool(
                        "gobby-tasks",
                        "reopen_task",
                        {"task_id": task_id},
                    )
                    self.notify(f"Task reopened: {task_id}")

                # Refresh after action
                await self.refresh_data()

        except Exception as e:
            self.notify(f"Action failed: {e}", severity="error")

    def on_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle WebSocket events."""
        if event_type == "hook_event":
            # Refresh on task-related hooks
            hook_type = data.get("event_type", "")
            if "task" in hook_type.lower():
                asyncio.create_task(self.refresh_data())

    def activate_search(self) -> None:
        """Activate search mode."""
        self.notify("Search not yet implemented", severity="information")
