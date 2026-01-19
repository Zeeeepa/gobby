"""Task tree widget for hierarchical task display."""

from __future__ import annotations

from typing import Any

from textual.widgets import Tree
from textual.widgets.tree import TreeNode


class TaskTree(Tree[str]):
    """Hierarchical tree view for tasks."""

    DEFAULT_CSS = """
    TaskTree {
        background: transparent;
    }

    TaskTree > .tree--cursor {
        background: #6d28d9;
    }

    TaskTree > .tree--guides {
        color: #45475a;
    }
    """

    STATUS_ICONS = {
        "open": "○",
        "in_progress": "◐",
        "review": "◑",
        "closed": "●",
        "blocked": "⊘",
    }

    TYPE_COLORS = {
        "task": "",
        "bug": "🐛 ",
        "feature": "✨ ",
        "epic": "🏔️ ",
    }

    def __init__(self, label: str = "Tasks", **kwargs: Any) -> None:
        super().__init__(label, **kwargs)
        self._task_map: dict[str, dict[str, Any]] = {}

    def populate(self, tasks: list[dict[str, Any]]) -> None:
        """Populate the tree with tasks."""
        self.clear()
        self._task_map = {task_id: t for t in tasks if (task_id := t.get("id"))}

        # Build parent -> children mapping
        children_map: dict[str | None, list[dict[str, Any]]] = {}
        for task in tasks:
            parent_id = task.get("parent_id")
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(task)

        # Add root level tasks
        root_tasks = children_map.get(None, [])
        for task in sorted(root_tasks, key=lambda t: t.get("priority", 3)):
            self._add_task_node(self.root, task, children_map)

        self.root.expand()

    def _add_task_node(
        self,
        parent: TreeNode[str],
        task: dict[str, Any],
        children_map: dict[str | None, list[dict[str, Any]]],
    ) -> None:
        """Add a task and its children to the tree."""
        status = task.get("status", "open")
        task_type = task.get("task_type", "task")

        icon = self.STATUS_ICONS.get(status, "○")
        type_prefix = self.TYPE_COLORS.get(task_type, "")
        ref = task.get("ref", "")
        title = task.get("title", "Untitled")

        label = f"{icon} {type_prefix}{ref} {title}"
        node = parent.add(label, data=task.get("id"))

        # Add children
        task_id = task.get("id")
        children = children_map.get(task_id, [])
        for child in sorted(children, key=lambda t: t.get("priority", 3)):
            self._add_task_node(node, child, children_map)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Get task data by ID."""
        return self._task_map.get(task_id)

    def get_selected_task_id(self) -> str | None:
        """Get the ID of the currently selected task."""
        if self.cursor_node:
            return self.cursor_node.data
        return None
