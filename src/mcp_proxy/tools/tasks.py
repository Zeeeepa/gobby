"""
Internal MCP tools for Gobby Task System.

Exposes functionality for:
- Task CRUD (create, get, update, close, delete, list)
- Dependencies (add, remove, tree, cycles)
- Ready Work (ready lists, blocked lists)
- Session Integration (link, get)
- Git Sync (trigger sync, status)
"""

from typing import Any

from gobby.storage.tasks import LocalTaskManager, Task
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.session_tasks import SessionTaskManager
from gobby.sync.tasks import TaskSyncManager
from mcp.server.fastmcp import FastMCP


def register_task_tools(
    mcp: FastMCP,
    task_manager: LocalTaskManager,
    sync_manager: TaskSyncManager,
) -> None:
    """
    Register task-related tools with the MCP server to expose them to agents.

    Args:
        mcp: FastMCP application instance
        task_manager: LocalTaskManager instance
        sync_manager: TaskSyncManager instance
    """
    # Helpers
    dep_manager = TaskDependencyManager(task_manager.db)
    session_task_manager = SessionTaskManager(task_manager.db)

    # --- Task CRUD ---

    @mcp.tool()
    def create_task(
        title: str,
        description: str | None = None,
        priority: int = 2,
        type: str = "task",
        parent_task_id: str | None = None,
        blocks: list[str] | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new task in the current project.

        Args:
            title: Task title
            description: Detailed description
            priority: Priority level (1=High, 2=Medium, 3=Low)
            type: Task type (task, bug, feature, epic)
            parent_task_id: Optional parent task ID
            blocks: List of task IDs that this new task blocks (optional)
            labels: List of labels (optional)
        """
        task = task_manager.create_task(
            title=title,
            description=description,
            priority=priority,
            task_type=type,
            parent_task_id=parent_task_id,
            labels=labels,
        )

        # Handle 'blocks' argument if provided (syntactic sugar)
        if blocks:
            for blocked_id in blocks:
                dep_manager.add_dependency(task.id, blocked_id, "blocks")

        return task.to_dict()

    @mcp.tool()
    def get_task(task_id: str) -> dict[str, Any]:
        """
        Get task details including dependencies.

        Args:
            task_id: The ID of the task to retrieve
        """
        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found", "found": False}

        result = task.to_dict()

        # Enrich with dependency info
        blockers = dep_manager.get_blockers(task_id)
        blocking = dep_manager.get_blocking(task_id)

        result["dependencies"] = {
            "blocked_by": [b.to_dict() for b in blockers],
            "blocking": [b.to_dict() for b in blocking],
        }

        return result

    @mcp.tool()
    def update_task(
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        assignee: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Update task fields.

        Args:
            task_id: Task ID
            title: New title
            description: New description
            status: New status (open, in_progress, closed)
            priority: New priority
            assignee: New assignee
            labels: New labels list
        """
        task = task_manager.update_task(
            task_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assignee=assignee,
            labels=labels,
        )
        if not task:
            return {"error": f"Task {task_id} not found"}
        return task.to_dict()

    @mcp.tool()
    def close_task(task_id: str, reason: str = "completed") -> dict[str, Any]:
        """
        Close a task with a reason.

        Args:
            task_id: Task ID
            reason: Reason for closing (e.g., "completed", "wont_fix", "duplicate")
        """
        if reason not in ["completed", "wont_fix", "duplicate"]:
            # Just a soft validation, can accept any string really but good to hint
            pass

        task = task_manager.close_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # If closing, maybe update description or add a comment log?
        # For now just update status via close_task method which handles it
        return task.to_dict()

    @mcp.tool()
    def delete_task(task_id: str, cascade: bool = False) -> dict[str, Any]:
        """
        Delete a task.

        Args:
            task_id: Task ID
            cascade: If True, delete all child tasks as well.
        """
        success = task_manager.delete_task(task_id, cascade=cascade)
        if not success:
            return {"error": f"Task {task_id} not found"}
        return {"success": True, "message": f"Task {task_id} deleted"}

    @mcp.tool()
    def list_tasks(
        status: str | None = None,
        priority: int | None = None,
        type: str | None = None,
        assignee: str | None = None,
        label: str | None = None,
        parent_task_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        List tasks with optional filters.

        Args:
            status: Filter by status
            priority: Filter by priority
            type: Filter by task type
            assignee: Filter by assignee
            label: Filter by label presence
            parent_task_id: Filter by parent task
            limit: Max number of tasks to return
        """
        tasks = task_manager.list_tasks(
            status=status,
            priority=priority,
            task_type=type,
            assignee=assignee,
            label=label,
            parent_task_id=parent_task_id,
            limit=limit,
        )
        return {"tasks": [t.to_dict() for t in tasks], "count": len(tasks)}

    # --- Dependencies ---

    @mcp.tool()
    def add_dependency(
        task_id: str,
        depends_on: str,
        dep_type: str = "blocks",
    ) -> dict[str, Any]:
        """
        Add a dependency between tasks.

        Args:
            task_id: The dependent task (e.g., Task B)
            depends_on: The blocker task (e.g., Task A)
            dep_type: Dependency type (default: "blocks")
        """
        try:
            dep_manager.add_dependency(task_id, depends_on, dep_type)
            return {"success": True, "message": f"Task {task_id} {dep_type} by {depends_on}"}
        except ValueError as e:
            return {"error": str(e)}

    @mcp.tool()
    def remove_dependency(task_id: str, depends_on: str) -> dict[str, Any]:
        """
        Remove a dependency.

        Args:
            task_id: The dependent task
            depends_on: The blocker task
        """
        dep_manager.remove_dependency(task_id, depends_on)
        return {"success": True, "message": "Dependency removed"}

    @mcp.tool()
    def get_dependency_tree(task_id: str, direction: str = "both") -> dict[str, Any]:
        """
        Get dependency tree.

        Args:
            task_id: Root task ID
            direction: "blockers" (upstream), "blocking" (downstream), or "both"
        """
        tree = dep_manager.get_dependency_tree(task_id)
        if direction == "blockers":
            return {"blockers": tree.get("blockers", [])}
        elif direction == "blocking":
            return {"blocking": tree.get("blocking", [])}
        return tree

    @mcp.tool()
    def check_dependency_cycles() -> dict[str, Any]:
        """
        Detect circular dependencies in the project.
        """
        cycles = dep_manager.check_cycles()
        if cycles:
            return {"has_cycles": True, "cycles": cycles}
        return {"has_cycles": False}

    # --- Ready Work ---

    @mcp.tool()
    def list_ready_tasks(
        priority: int | None = None,
        type: str | None = None,
        assignee: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        List tasks that are open and have no unresolved blocking dependencies.

        Args:
            priority: Filter by priority
            type: Filter by type
            assignee: Filter by assignee
            limit: Max results
        """
        tasks = task_manager.list_ready_tasks(
            priority=priority,
            task_type=type,
            assignee=assignee,
            limit=limit,
        )
        return {"tasks": [t.to_dict() for t in tasks], "count": len(tasks)}

    @mcp.tool()
    def list_blocked_tasks(limit: int = 20) -> dict[str, Any]:
        """
        List tasks that are currently blocked, including what blocks them.

        Args:
            limit: Max results
        """
        # This requires a method in LocalTaskManager that joins with dependencies
        # Since we implemented list_blocked_tasks in Phase 3, we can use it.
        blocked_items = task_manager.list_blocked_tasks(limit=limit)
        return {"blocked_tasks": blocked_items}

    # --- Session Integration ---

    @mcp.tool()
    def link_task_to_session(
        task_id: str,
        session_id: str | None = None,
        action: str = "worked_on",
    ) -> dict[str, Any]:
        """
        Link a task to a session.

        Args:
            task_id: Task ID
            session_id: Session ID (optional, defaults to linking context if available, but here must be explicit or derived)
            action: Relationship type (worked_on, discovered, mentioned, closed)
        """
        if not session_id:
            # In a real agent context, we might infer this from the MCP request context
            # For now, we require it or return error if we can't get it.
            return {"error": "session_id is required"}

        try:
            session_task_manager.link_task(session_id, task_id, action)
            return {"success": True, "message": f"Task {task_id} linked to session {session_id}"}
        except ValueError as e:
            return {"error": str(e)}

    @mcp.tool()
    def get_session_tasks(session_id: str) -> dict[str, Any]:
        """
        Get all tasks associated with a session.

        Args:
            session_id: Session ID
        """
        tasks = session_task_manager.get_session_tasks(session_id)
        return {"session_id": session_id, "tasks": tasks}

    @mcp.tool()
    def get_task_sessions(task_id: str) -> dict[str, Any]:
        """
        Get all sessions that touched a task.

        Args:
            task_id: Task ID
        """
        sessions = session_task_manager.get_task_sessions(task_id)
        return {"task_id": task_id, "sessions": sessions}

    # --- Git Sync ---

    @mcp.tool()
    def sync_tasks(direction: str = "both") -> dict[str, Any]:
        """
        Manually trigger task synchronization.

        Args:
            direction: "import", "export", or "both"
        """
        result = {}
        if direction in ["import", "both"]:
            sync_manager.import_from_jsonl()
            result["import"] = "completed"

        if direction in ["export", "both"]:
            sync_manager.export_to_jsonl()
            result["export"] = "completed"

        return result

    @mcp.tool()
    def get_sync_status() -> dict[str, Any]:
        """
        Get current synchronization status.
        """
        return sync_manager.get_sync_status()
